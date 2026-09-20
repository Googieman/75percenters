"""Evidence-gated CampusWeb Student Portal provider.

The provider deliberately implements only CampusWeb's Student Portal route. It
does not try the site's Academia login, and it never returns upstream response
bodies or credentials to callers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from srm_tracker.acquisition_provider import HostedSyncResult, ProviderChallenge, ProviderSession
from srm_tracker.schemas import AttendanceUpload

CAMPUSWEB_STUDENT_PORTAL = "campusweb_student_portal"
CAMPUSWEB_API_BASE_URL = "https://campusapi.fly.dev"
LOGIN_PATH = "/api/student-portal/login"
ATTENDANCE_PATH = "/api/student-portal/attendance"
IDENTITY_PATH = "/api/auth/user/"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30.0


class CampusWebProviderError(RuntimeError):
    """Base class for safe provider failures."""


class ProviderAuthenticationError(CampusWebProviderError):
    """CampusWeb rejected credentials or the active session."""


class ProviderReauthenticationRequired(CampusWebProviderError):
    """CampusWeb no longer accepts the stored session."""


class ProviderTransientFailure(CampusWebProviderError):
    """The request can be retried without changing stored account state."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderContractChanged(CampusWebProviderError):
    """The upstream response is not the verified Student Portal contract."""


@dataclass(frozen=True, slots=True)
class _Response:
    status_code: int
    headers: httpx.Headers
    content: bytes


class CampusWebProvider:
    """A fixed-destination, bounded CampusWeb Student Portal client."""

    name = CAMPUSWEB_STUDENT_PORTAL

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            follow_redirects=False,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )

    def start_authentication(self, netid: str) -> ProviderChallenge:
        normalized = _normalize_netid(netid)
        return ProviderChallenge(
            challenge_type="password",
            message="Enter your CampusWeb password. It is forwarded only for this connection.",
            state=json.dumps({"netid": normalized}, separators=(",", ":")).encode("utf-8"),
        )

    def complete_authentication(
        self,
        challenge: ProviderChallenge,
        password: str,
        response: str | None,
    ) -> ProviderSession:
        del response
        netid = _challenge_netid(challenge)
        result = self._request_json(
            "POST",
            LOGIN_PATH,
            operation="login",
            json_body={"net_id": netid, "password": password},
        )
        if result.status_code in {401, 403}:
            raise ProviderAuthenticationError("CampusWeb credentials were rejected")
        if result.status_code == 429 or result.status_code >= 500:
            raise ProviderTransientFailure(
                "CampusWeb login is temporarily unavailable", _retry_after(result)
            )
        payload = _require_success(result, "login")
        if not result.headers.get("set-cookie") or not self._client.cookies:
            raise ProviderContractChanged("CampusWeb login returned no authenticated session")

        csrf_token = _optional_string(payload, ("csrf_token", "csrfToken", "Cookies", "cookies"))
        identity_payload = self._request_json(
            "GET",
            IDENTITY_PATH,
            operation="identity",
            headers=_identity_headers(netid, csrf_token),
        )
        if identity_payload.status_code in {401, 403}:
            raise ProviderAuthenticationError("CampusWeb session could not be verified")
        identity = _require_success(identity_payload, "identity")
        verified_netid, term_context = _identity_evidence(identity)
        _require_same_identity(netid, verified_netid)
        return ProviderSession(
            state=_serialize_session(self._client, netid, csrf_token),
            verified_netid=verified_netid,
            term_context=term_context,
        )

    def fetch_attendance(self, session: ProviderSession) -> HostedSyncResult:
        netid, csrf_token = _restore_session(self._client, session.state)
        identity_payload = self._request_json(
            "GET",
            IDENTITY_PATH,
            operation="identity",
            headers=_identity_headers(netid, csrf_token),
        )
        if identity_payload.status_code in {401, 403}:
            raise ProviderReauthenticationRequired("CampusWeb session expired")
        identity = _require_success(identity_payload, "identity")
        verified_netid, term_context = _identity_evidence(identity)
        _require_same_identity(session.verified_netid, verified_netid)
        if term_context != session.term_context:
            raise ProviderContractChanged("CampusWeb semester changed")

        attendance_response = self._request_json(
            "POST",
            ATTENDANCE_PATH,
            operation="attendance",
            json_body={"net_id": netid},
            headers=_identity_headers(netid, csrf_token),
        )
        if attendance_response.status_code in {401, 403}:
            raise ProviderReauthenticationRequired("CampusWeb session expired")
        payload = _require_success(attendance_response, "attendance")
        batch = _attendance_upload(payload, term_context)
        return HostedSyncResult(
            batch=batch,
            term_context=term_context,
            session_state=_serialize_session(self._client, netid, csrf_token),
        )

    def disconnect(self, session: ProviderSession) -> None:
        del session
        # CampusWeb's public contract does not expose a verified logout endpoint.
        # The caller clears our encrypted state; no guessed logout request is sent.

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        json_body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> _Response:
        try:
            with self._client.stream(
                method,
                f"{CAMPUSWEB_API_BASE_URL}{path}",
                json=json_body,
                headers=headers,
            ) as response:
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ProviderContractChanged("CampusWeb response too large")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if "json" not in response.headers.get("content-type", "").lower():
                    raise ProviderContractChanged(f"unexpected {operation} response")
                return _Response(response.status_code, response.headers, content)
        except ProviderContractChanged:
            raise
        except httpx.TimeoutException as error:
            raise ProviderTransientFailure("CampusWeb request timed out") from error
        except httpx.HTTPError as error:
            raise ProviderTransientFailure("CampusWeb request failed") from error


def _normalize_netid(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 128:
        raise ProviderAuthenticationError("CampusWeb identity is invalid")
    return normalized


def _challenge_netid(challenge: ProviderChallenge) -> str:
    if not challenge.state:
        raise ProviderAuthenticationError("CampusWeb authentication challenge is unavailable")
    try:
        state = json.loads(challenge.state)
        netid = state["netid"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProviderAuthenticationError(
            "CampusWeb authentication challenge is unavailable"
        ) from error
    if not isinstance(netid, str):
        raise ProviderAuthenticationError("CampusWeb authentication challenge is unavailable")
    return _normalize_netid(netid)


def _require_success(response: _Response, operation: str) -> dict[str, Any]:
    try:
        payload = json.loads(response.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderContractChanged(f"unexpected {operation} response") from error
    if not isinstance(payload, dict):
        raise ProviderContractChanged(f"unexpected {operation} response")
    if response.status_code < 200 or response.status_code >= 300:
        if operation == "login" and response.status_code in {400, 422}:
            raise ProviderAuthenticationError("CampusWeb credentials were rejected")
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderTransientFailure(
                f"CampusWeb {operation} is temporarily unavailable", _retry_after(response)
            )
        raise ProviderContractChanged(f"unexpected {operation} response")
    if payload.get("status") != "success":
        if operation == "login":
            raise ProviderAuthenticationError("CampusWeb credentials were rejected")
        raise ProviderContractChanged(f"unexpected {operation} response")
    return payload


def _identity_headers(netid: str, csrf_token: str | None) -> dict[str, str]:
    headers = {"X-Net-ID": netid}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    return headers


def _retry_after(response: _Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return max(0, min(seconds, 24 * 60 * 60))


def _optional_string(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _optional_string(data, keys)
    return None


def _identity_evidence(payload: Mapping[str, Any]) -> tuple[str, str]:
    candidates: list[Mapping[str, Any]] = [payload]
    for key in ("data", "user", "student"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)
    identity_keys = ("net_id", "netId", "netid", "username")
    term_keys = ("semester", "term", "semester_name", "current_semester")
    netid = next(
        (
            value
            for candidate in candidates
            for key in identity_keys
            if isinstance((value := candidate.get(key)), str)
        ),
        None,
    )
    term = next(
        (
            value
            for candidate in candidates
            for key in term_keys
            if isinstance((value := candidate.get(key)), str)
        ),
        None,
    )
    if not netid or not term:
        raise ProviderContractChanged("CampusWeb identity or semester evidence is missing")
    return _normalize_netid(netid), " ".join(term.split())


def _require_same_identity(requested: str, verified: str) -> None:
    if requested.casefold() != verified.casefold():
        raise ProviderContractChanged("CampusWeb identity did not match the requested account")


def _attendance_upload(payload: Mapping[str, Any], term_context: str) -> AttendanceUpload:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ProviderContractChanged("unexpected CampusWeb attendance response")
    attendance_term = data.get("semester", data.get("term"))
    if not isinstance(attendance_term, str) or " ".join(attendance_term.split()) != term_context:
        raise ProviderContractChanged("CampusWeb attendance semester changed")
    raw_subjects = data.get("subjects")
    if not isinstance(raw_subjects, list) or not raw_subjects:
        raise ProviderContractChanged("unexpected CampusWeb attendance response")
    try:
        return AttendanceUpload.model_validate({"subjects": raw_subjects})
    except (TypeError, ValidationError) as error:
        raise ProviderContractChanged("invalid CampusWeb attendance data") from error


def _serialize_session(client: httpx.Client, netid: str, csrf_token: str | None) -> bytes:
    cookies = [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
        }
        for cookie in client.cookies.jar
    ]
    return json.dumps(
        {"netid": netid, "csrf_token": csrf_token, "cookies": cookies},
        separators=(",", ":"),
    ).encode("utf-8")


def _restore_session(client: httpx.Client, state: bytes) -> tuple[str, str | None]:
    try:
        payload = json.loads(state)
        netid = payload["netid"]
        csrf_token = payload.get("csrf_token")
        cookies = payload["cookies"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProviderContractChanged("stored CampusWeb session is invalid") from error
    if not isinstance(netid, str) or not isinstance(cookies, list):
        raise ProviderContractChanged("stored CampusWeb session is invalid")
    client.cookies.clear()
    for cookie in cookies:
        if not isinstance(cookie, Mapping):
            raise ProviderContractChanged("stored CampusWeb session is invalid")
        name, value = cookie.get("name"), cookie.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ProviderContractChanged("stored CampusWeb session is invalid")
        domain = cookie.get("domain")
        path = cookie.get("path")
        cookie_path = path if isinstance(path, str) else "/"
        if isinstance(domain, str):
            client.cookies.set(name, value, domain=domain, path=cookie_path)
        else:
            client.cookies.set(name, value, path=cookie_path)
    if csrf_token is not None and not isinstance(csrf_token, str):
        raise ProviderContractChanged("stored CampusWeb session is invalid")
    return _normalize_netid(netid), csrf_token
