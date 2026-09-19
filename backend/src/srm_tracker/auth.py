"""Personal account sessions, CSRF, and authentication routes."""

from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.config import Settings
from srm_tracker.db import get_request_db
from srm_tracker.db_models import Session as AuthSession
from srm_tracker.db_models import User
from srm_tracker.rate_limit import RateLimitExceeded, consume_rate_limit
from srm_tracker.security import hash_opaque_token, new_opaque_token, verify_password
from srm_tracker.time import utc_now

router = APIRouter(prefix="/api/v1/auth", tags=["sessions"])
CSRF_COOKIE_NAME = "srm_tracker_csrf"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: int
    email: str
    attendance_target: float


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session: AuthSession
    csrf_token: str | None


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        attendance_target=float(user.attendance_target),
    )


def _rate_limit_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return hash_opaque_token(f"login:{host}:{email.strip().casefold()}")


def _rate_limit_error(error: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many attempts; try again later",
        headers={"Retry-After": str(error.retry_after)},
    )


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def _set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=False,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def get_current_auth(
    request: Request,
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthContext:
    """Authenticate only the HTTP-only browser session cookie."""
    settings = _settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_opaque_token(raw_token))
    )
    if (
        auth_session is None
        or auth_session.invalidated_at is not None
        or auth_session.expires_at <= utc_now()
        or auth_session.user is None
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return AuthContext(
        user=auth_session.user,
        session=auth_session,
        csrf_token=request.cookies.get(CSRF_COOKIE_NAME),
    )


def require_csrf(
    request: Request,
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
) -> AuthContext:
    """Require the session-bound double-submit token on browser writes."""
    raw_csrf = request.headers.get("X-CSRF-Token")
    if not raw_csrf or hash_opaque_token(raw_csrf) != context.session.csrf_token_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return context


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthResponse:
    email = payload.email.strip().casefold()
    try:
        consume_rate_limit(
            session,
            action="login",
            key=_rate_limit_key(request, email),
            max_attempts=_settings(request).login_rate_limit_attempts,
            window_seconds=_settings(request).rate_limit_window_seconds,
        )
    except RateLimitExceeded as error:
        raise _rate_limit_error(error) from error

    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    raw_session = new_opaque_token()
    raw_csrf = new_opaque_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_opaque_token(raw_session),
        csrf_token_hash=hash_opaque_token(raw_csrf),
        expires_at=utc_now() + timedelta(days=_settings(request).session_ttl_days),
    )
    session.add(auth_session)
    session.commit()
    settings = _settings(request)
    _set_session_cookie(response, settings, raw_session)
    _set_csrf_cookie(response, settings, raw_csrf)
    return AuthResponse(user=_user_response(user), csrf_token=raw_csrf)


@router.get("/me", response_model=AuthResponse)
def me(context: AuthContext = Depends(get_current_auth)) -> AuthResponse:  # noqa: B008
    return AuthResponse(user=_user_response(context.user), csrf_token=context.csrf_token or "")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> None:
    context.session.invalidated_at = utc_now()
    session.commit()
    settings = _settings(request)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
