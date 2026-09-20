import json

import httpx
import pytest

from srm_tracker.campusweb_provider import (
    CAMPUSWEB_STUDENT_PORTAL,
    CampusWebProvider,
    ProviderAuthenticationError,
    ProviderContractChanged,
    ProviderTransientFailure,
)
from srm_tracker.schemas import AttendanceUpload


def _provider(handler: object) -> CampusWebProvider:
    return CampusWebProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            timeout=30.0,
        )
    )


def _success_payload() -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "net_id": "AB1234",
            "semester": "2026-T1",
        },
    }


def _attendance_payload() -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "semester": "2026-T1",
            "subjects": [
                {
                    "code": "CSE1",
                    "subject": "Algorithms",
                    "total_hours": 10,
                    "attended_hours": 8,
                    "absent_hours": 2,
                    "source_percentage": "80.00",
                }
            ],
        },
    }


def test_student_portal_login_and_attendance_never_try_academia() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/student-portal/login":
            assert json.loads(request.content) == {"net_id": "AB1234", "password": "secret"}
            return httpx.Response(
                200,
                json={"status": "success", "csrf_token": "rotated-csrf"},
                headers={"set-cookie": "sp_session=opaque-session; Path=/; HttpOnly"},
                request=request,
            )
        if request.url.path == "/api/auth/user/":
            assert request.headers["x-net-id"] == "AB1234"
            return httpx.Response(200, json=_success_payload(), request=request)
        if request.url.path == "/api/student-portal/attendance":
            assert json.loads(request.content) == {"net_id": "AB1234"}
            return httpx.Response(
                200,
                json=_attendance_payload(),
                headers={"set-cookie": "sp_session=rotated-session; Path=/; HttpOnly"},
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    provider = _provider(handler)
    challenge = provider.start_authentication("AB1234")
    assert challenge.challenge_type == "password"
    assert provider.name == CAMPUSWEB_STUDENT_PORTAL

    session = provider.complete_authentication(challenge, "secret", None)
    assert session.verified_netid == "AB1234"
    assert session.term_context == "2026-T1"

    result = provider.fetch_attendance(session)
    assert isinstance(result.batch, AttendanceUpload)
    assert result.batch.subjects[0].code == "CSE1"
    assert result.term_context == "2026-T1"
    assert result.session_state is not None
    assert b"rotated-session" in result.session_state
    assert all(request.url.path != "/api/auth/login/" for request in requests)


def test_rejected_credentials_are_safe_and_do_not_expose_upstream_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"message": "the password=secret-value is invalid"},
            request=request,
        )

    with pytest.raises(ProviderAuthenticationError) as error:
        _provider(handler).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )

    assert "secret-value" not in str(error.value)
    assert "password" not in str(error.value).lower()


def test_login_html_is_a_contract_failure_even_when_status_is_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login page</html>", request=request)

    with pytest.raises(ProviderContractChanged, match="unexpected login response"):
        _provider(handler).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )


def test_identity_mismatch_and_malformed_counts_fail_closed() -> None:
    def mismatched(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200,
                json={"status": "success"},
                headers={"set-cookie": "sp_session=opaque; Path=/"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"status": "success", "data": {"net_id": "ZZ9999", "semester": "2026-T1"}},
            request=request,
        )

    with pytest.raises(ProviderContractChanged, match="identity"):
        _provider(mismatched).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )

    def malformed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200,
                json={"status": "success"},
                headers={"set-cookie": "sp_session=opaque; Path=/"},
                request=request,
            )
        if request.url.path.endswith("/user/"):
            return httpx.Response(200, json=_success_payload(), request=request)
        payload = _attendance_payload()
        payload["data"]["subjects"][0]["attended_hours"] = "8.5"  # type: ignore[index]
        return httpx.Response(200, json=payload, request=request)

    provider = _provider(malformed)
    session = provider.complete_authentication(
        provider.start_authentication("AB1234"), "secret", None
    )
    with pytest.raises(ProviderContractChanged, match="attendance"):
        provider.fetch_attendance(session)

    payload = _attendance_payload()
    payload["data"]["semester"] = "2026-T2"  # type: ignore[index]

    def changed_term(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200,
                json={"status": "success"},
                headers={"set-cookie": "sp_session=opaque; Path=/"},
                request=request,
            )
        if request.url.path.endswith("/user/"):
            return httpx.Response(200, json=_success_payload(), request=request)
        return httpx.Response(200, json=payload, request=request)

    changed_provider = _provider(changed_term)
    changed_session = changed_provider.complete_authentication(
        changed_provider.start_authentication("AB1234"), "secret", None
    )
    with pytest.raises(ProviderContractChanged, match="semester"):
        changed_provider.fetch_attendance(changed_session)


def test_oversized_upstream_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + b"a" * (2 * 1024 * 1024) + b"}", request=request)

    with pytest.raises(ProviderContractChanged, match="response too large"):
        _provider(handler).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )


def test_missing_authenticated_session_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success"}, request=request)

    with pytest.raises(ProviderContractChanged, match="authenticated session"):
        _provider(handler).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )


def test_timeout_is_safe_and_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timeout", request=request)

    with pytest.raises(ProviderTransientFailure) as error:
        _provider(handler).complete_authentication(
            CampusWebProvider().start_authentication("AB1234"), "secret", None
        )

    assert "timed out" in str(error.value)
    assert "upstream" not in str(error.value)
