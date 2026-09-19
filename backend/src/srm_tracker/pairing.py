"""One-time connector pairing and device management."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.auth import AuthContext, get_current_auth, require_csrf
from srm_tracker.config import Settings
from srm_tracker.db import get_request_db
from srm_tracker.db_models import ConnectorDevice, PairingCode
from srm_tracker.rate_limit import RateLimitExceeded, consume_rate_limit
from srm_tracker.security import hash_opaque_token, new_opaque_token
from srm_tracker.time import utc_now

router = APIRouter(tags=["pairing"])


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=255)
    name: str = Field(default="Chrome connector", min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("device name must not be blank")
        return value


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class DeviceResponse(BaseModel):
    device_id: int
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class PairResponse(DeviceResponse):
    device_token: str


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    device: ConnectorDevice


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def create_pairing_code(
    session: DbSession,
    user_id: int,
    ttl_minutes: int = 10,
) -> tuple[str, PairingCode]:
    """Create a hashed, short-lived code and return its clear value exactly once."""
    raw_code = new_opaque_token()
    pairing = PairingCode(
        user_id=user_id,
        code_hash=hash_opaque_token(raw_code),
        expires_at=utc_now() + timedelta(minutes=ttl_minutes),
    )
    session.add(pairing)
    session.commit()
    session.refresh(pairing)
    return raw_code, pairing


def exchange_pairing_code(
    session: DbSession,
    code: str,
    name: str = "Chrome connector",
) -> tuple[ConnectorDevice, str]:
    """Atomically consume a code and create one revocable connector device."""
    pairing = session.scalar(
        select(PairingCode)
        .where(PairingCode.code_hash == hash_opaque_token(code))
        .with_for_update()
    )
    now = utc_now()
    if pairing is None or pairing.consumed_at is not None:
        raise ValueError("invalid or already-used pairing code")
    if pairing.expires_at <= now:
        raise ValueError("pairing code expired")

    raw_token = new_opaque_token()
    pairing.consumed_at = now
    device = ConnectorDevice(
        user_id=pairing.user_id,
        name=name.strip() or "Chrome connector",
        token_hash=hash_opaque_token(raw_token),
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device, raw_token


def get_connector_context(
    request: Request,
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> ConnectorContext:
    """Authenticate only a non-revoked connector bearer token."""
    authorization = request.headers.get("Authorization", "")
    scheme, separator, raw_token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not separator or not raw_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid connector token"
        )
    device = session.scalar(
        select(ConnectorDevice).where(
            ConnectorDevice.token_hash == hash_opaque_token(raw_token.strip()),
            ConnectorDevice.revoked_at.is_(None),
        )
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid connector token"
        )
    return ConnectorContext(device=device)


def _device_response(device: ConnectorDevice) -> DeviceResponse:
    return DeviceResponse(
        device_id=device.id,
        name=device.name,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
    )


@router.post("/api/v1/pairing-codes", response_model=PairingCodeResponse)
def issue_pairing_code(
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> PairingCodeResponse:
    raw_code, pairing = create_pairing_code(
        session,
        context.user.id,
        ttl_minutes=_settings(request).pairing_ttl_minutes,
    )
    return PairingCodeResponse(code=raw_code, expires_at=pairing.expires_at)


@router.post("/api/v1/connector/pair", response_model=PairResponse)
def pair_connector(
    payload: PairRequest,
    request: Request,
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> PairResponse:
    host = request.client.host if request.client else "unknown"
    try:
        consume_rate_limit(
            session,
            action="pairing",
            key=hash_opaque_token(f"pairing:{host}"),
            max_attempts=_settings(request).pairing_rate_limit_attempts,
            window_seconds=_settings(request).rate_limit_window_seconds,
        )
        device, raw_token = exchange_pairing_code(session, payload.code, payload.name)
    except RateLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many pairing attempts; try again later",
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return PairResponse(
        **_device_response(device).model_dump(),
        device_token=raw_token,
    )


@router.get("/api/v1/devices", response_model=list[DeviceResponse])
def list_devices(
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> list[DeviceResponse]:
    devices = session.scalars(
        select(ConnectorDevice)
        .where(ConnectorDevice.user_id == context.user.id)
        .order_by(ConnectorDevice.created_at.desc(), ConnectorDevice.id.desc())
    )
    return [_device_response(device) for device in devices]


@router.delete("/api/v1/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(
    device_id: int,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> None:
    device = session.scalar(
        select(ConnectorDevice).where(
            ConnectorDevice.id == device_id,
            ConnectorDevice.user_id == context.user.id,
        )
    )
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    device.revoked_at = utc_now()
    session.commit()
