"""Phone-facing SRM connection, sync, and Web Push API."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.acquisition_crypto import (
    SessionCipherError,
    SessionKeyring,
    keyring_from_settings,
)
from srm_tracker.acquisition_provider import AcquisitionProvider, ProviderChallenge, ProviderSession
from srm_tracker.acquisition_service import (
    AuthAttemptError,
    IdentityConflictError,
    consume_auth_attempt,
    create_auth_attempt,
    disconnect_connection,
    fail_auth_attempt,
    get_connection,
    netid_hint,
    promote_authenticated_session,
    upsert_push_subscription,
)
from srm_tracker.auth import AuthContext, get_current_auth, require_csrf
from srm_tracker.campusweb_provider import (
    CAMPUSWEB_STUDENT_PORTAL,
    CampusWebProviderError,
    ProviderAuthenticationError,
    ProviderContractChanged,
    ProviderTransientFailure,
)
from srm_tracker.campusweb_worker import CampusWebSyncExecutor
from srm_tracker.config import Settings
from srm_tracker.db import get_request_db
from srm_tracker.db_models import AuthAttempt, PushSubscription, SyncJob
from srm_tracker.rate_limit import RateLimitExceeded, consume_rate_limit
from srm_tracker.schemas import (
    AuthAttemptCompleteRequest,
    AuthAttemptResponse,
    AuthAttemptStartRequest,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
    SrmConnectionResponse,
    SyncJobResponse,
)
from srm_tracker.security import hash_opaque_token
from srm_tracker.session_store import decrypt_attempt_state, store_attempt_state
from srm_tracker.sync_jobs import (
    ConnectionRequiredError,
    SyncTooSoonError,
    enqueue_sync_job,
)
from srm_tracker.worker import SyncWorker

router = APIRouter(tags=["srm-acquisition"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _require_acquisition_enabled(request: Request) -> None:
    if not _settings(request).acquisition_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted acquisition is disabled until a provider passes the verification gates",
        )


def _provider(request: Request) -> AcquisitionProvider:
    provider = getattr(request.app.state, "acquisition_provider", None)
    if provider is None or getattr(provider, "name", None) != CAMPUSWEB_STUDENT_PORTAL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No verified CampusWeb Student Portal provider is configured",
        )
    return cast(AcquisitionProvider, provider)


def _cipher(request: Request) -> SessionKeyring:
    encoded = _settings(request).session_encryption_key
    if not encoded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted acquisition encryption is not configured",
        )
    try:
        return keyring_from_settings(
            encoded,
            active_version=_settings(request).session_encryption_key_version,
            read_keys_json=_settings(request).session_encryption_read_keys,
        )
    except SessionCipherError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted acquisition encryption is unavailable",
        ) from error


def _attempt_response(attempt: AuthAttempt) -> AuthAttemptResponse:
    return AuthAttemptResponse(
        attempt_id=attempt.id,
        status=attempt.status,
        challenge_type=attempt.challenge_type,
        message=attempt.display_message,
        expires_at=attempt.expires_at,
    )


def _job_response(job: SyncJob) -> SyncJobResponse:
    return SyncJobResponse(
        job_id=job.id,
        status=job.status,
        scheduled_for=job.scheduled_for,
        attempt_count=job.attempt_count,
        result_code=job.result_code,
        retry_at=job.retry_at,
        completed_at=job.completed_at,
    )


def _run_on_demand_sync(request: Request) -> None:
    factory = request.app.state.session_factory
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted refresh is unavailable",
        )
    keyring = _cipher(request)
    worker = SyncWorker(
        factory,
        CampusWebSyncExecutor(factory, _provider(request), keyring),
        scheduled_interval_minutes=_settings(request).sync_hourly_interval_minutes,
        cipher=keyring,
    )
    try:
        worker.run_once()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted refresh is temporarily unavailable",
        ) from None


@router.get("/api/v1/srm/connection", response_model=SrmConnectionResponse)
def connection_status(
    request: Request,
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> SrmConnectionResponse:
    connection = get_connection(session, context.user.id)
    active_job = session.scalar(
        select(SyncJob)
        .where(
            SyncJob.user_id == context.user.id,
            SyncJob.status.in_(("queued", "claimed")),
        )
        .order_by(SyncJob.scheduled_for, SyncJob.id)
    )
    return SrmConnectionResponse(
        status=connection.status if connection is not None else "disconnected",
        provider=connection.provider if connection is not None else None,
        provider_available=(
            _settings(request).acquisition_enabled
            and getattr(getattr(request.app.state, "acquisition_provider", None), "name", None)
            == CAMPUSWEB_STUDENT_PORTAL
        ),
        sync_mode=_settings(request).sync_execution_mode,
        netid_hint=netid_hint(connection.verified_netid) if connection is not None else None,
        last_authenticated_at=(
            connection.last_authenticated_at if connection is not None else None
        ),
        last_refreshed_at=(connection.last_refreshed_at if connection is not None else None),
        last_successful_sync=context.user.last_successful_sync_at,
        active_job_id=active_job.id if active_job is not None else None,
        next_scheduled_refresh=(
            active_job.scheduled_for
            if active_job is not None
            else connection.next_scheduled_refresh if connection is not None else None
        ),
        last_error_code=connection.last_error_code if connection is not None else None,
        notifications_available=bool(
            _settings(request).web_push_public_key
            and _settings(request).web_push_private_key
            and _settings(request).web_push_subject
        ),
    )


@router.post("/api/v1/srm/auth-attempts", response_model=AuthAttemptResponse, status_code=201)
def start_auth_attempt(
    payload: AuthAttemptStartRequest,
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthAttemptResponse:
    _require_acquisition_enabled(request)
    provider = _provider(request)
    cipher = _cipher(request)
    try:
        consume_rate_limit(
            session,
            action="srm_auth",
            key=hash_opaque_token(f"{context.user.id}:{payload.netid.casefold()}"),
            max_attempts=_settings(request).login_rate_limit_attempts,
            window_seconds=_settings(request).rate_limit_window_seconds,
        )
        attempt = create_auth_attempt(
            session,
            context.user.id,
            provider=CAMPUSWEB_STUDENT_PORTAL,
            netid=payload.netid,
            ttl_seconds=600,
        )
    except RateLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many connection attempts; try again later",
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    except IdentityConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    try:
        challenge = provider.start_authentication(payload.netid)
        attempt.challenge_type = challenge.challenge_type
        attempt.display_message = challenge.message
        if challenge.state is not None:
            store_attempt_state(attempt, cipher, challenge.state)
        session.commit()
        session.refresh(attempt)
        return _attempt_response(attempt)
    except CampusWebProviderError as error:
        fail_auth_attempt(
            session,
            context.user.id,
            attempt.id,
            status="failed",
            message="CampusWeb connection failed",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CampusWeb connection failed",
        ) from error


@router.post("/api/v1/srm/auth-attempts/{attempt_id}/complete", response_model=AuthAttemptResponse)
def complete_auth_attempt(
    attempt_id: int,
    payload: AuthAttemptCompleteRequest,
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthAttemptResponse:
    _require_acquisition_enabled(request)
    provider = _provider(request)
    cipher = _cipher(request)
    try:
        attempt = consume_auth_attempt(session, context.user.id, attempt_id)
    except AuthAttemptError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    try:
        challenge_state = decrypt_attempt_state(attempt, cipher)
        provider_result = provider.complete_authentication(
            ProviderChallenge(attempt.challenge_type, attempt.display_message, challenge_state),
            payload.password or "",
            payload.response,
        )
        if not isinstance(provider_result, ProviderSession):
            raise ProviderContractChanged("CampusWeb requested an unsupported challenge")
        promoted, _job = promote_authenticated_session(
            session,
            context.user.id,
            attempt_id,
            provider_result,
            provider=CAMPUSWEB_STUDENT_PORTAL,
            cipher=cipher,
        )
        return _attempt_response(promoted)
    except ProviderAuthenticationError as error:
        failed = fail_auth_attempt(
            session,
            context.user.id,
            attempt_id,
            status="failed",
            message="CampusWeb credentials were rejected",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=failed.display_message,
        ) from error
    except ProviderTransientFailure as error:
        fail_auth_attempt(
            session,
            context.user.id,
            attempt_id,
            status="failed",
            message="CampusWeb is temporarily unavailable",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CampusWeb is temporarily unavailable",
        ) from error
    except (
        AuthAttemptError,
        ProviderContractChanged,
        IdentityConflictError,
        SessionCipherError,
    ) as error:
        fail_auth_attempt(
            session,
            context.user.id,
            attempt_id,
            status="failed",
            message="CampusWeb account verification failed",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CampusWeb account verification failed",
        ) from error
    except CampusWebProviderError as error:
        fail_auth_attempt(
            session,
            context.user.id,
            attempt_id,
            status="failed",
            message="CampusWeb connection failed",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CampusWeb connection failed",
        ) from error


@router.delete("/api/v1/srm/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> None:
    disconnect_connection(session, context.user.id)


@router.post(
    "/api/v1/srm/sync", response_model=SyncJobResponse, status_code=status.HTTP_202_ACCEPTED
)
def queue_sync(
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> SyncJobResponse:
    _require_acquisition_enabled(request)
    try:
        job = enqueue_sync_job(
            session,
            context.user.id,
            kind="manual",
            minimum_interval_minutes=_settings(request).sync_minimum_interval_minutes,
        )
    except ConnectionRequiredError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except SyncTooSoonError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
            headers={"Retry-After": str(error.retry_after)},
        ) from error
    if _settings(request).sync_execution_mode == "on_demand":
        # The worker uses a separate session and must not wait on the route
        # session's implicit transaction while it claims the user row.
        session.commit()
        _run_on_demand_sync(request)
        session.refresh(job)
    return _job_response(job)


@router.get("/api/v1/srm/sync-jobs/{job_id}", response_model=SyncJobResponse)
def get_sync_job(
    job_id: int,
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> SyncJobResponse:
    job = session.scalar(
        select(SyncJob).where(SyncJob.id == job_id, SyncJob.user_id == context.user.id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found")
    return _job_response(job)


@router.post("/api/v1/push-subscriptions", response_model=PushSubscriptionResponse)
def register_push_subscription(
    payload: PushSubscriptionRequest,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> PushSubscriptionResponse:
    subscription = upsert_push_subscription(
        session,
        context.user.id,
        endpoint=str(payload.endpoint),
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return PushSubscriptionResponse(subscription_id=subscription.id)


@router.delete(
    "/api/v1/push-subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_push_subscription(
    subscription_id: int,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> None:
    subscription = session.scalar(
        select(PushSubscription).where(
            PushSubscription.id == subscription_id,
            PushSubscription.user_id == context.user.id,
        )
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    session.delete(subscription)
    session.commit()
