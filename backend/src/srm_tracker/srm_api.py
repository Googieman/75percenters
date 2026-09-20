"""Phone-facing SRM connection, sync, and Web Push API."""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.acquisition_service import (
    AuthAttemptError,
    consume_auth_attempt,
    disconnect_connection,
    get_connection,
    netid_hint,
    upsert_push_subscription,
)
from srm_tracker.auth import AuthContext, get_current_auth, require_csrf
from srm_tracker.config import Settings
from srm_tracker.db import get_request_db
from srm_tracker.db_models import PushSubscription, SyncJob
from srm_tracker.schemas import (
    AuthAttemptCompleteRequest,
    AuthAttemptResponse,
    AuthAttemptStartRequest,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
    SrmConnectionResponse,
    SyncJobResponse,
)
from srm_tracker.sync_jobs import (
    ConnectionRequiredError,
    SyncTooSoonError,
    enqueue_sync_job,
)

router = APIRouter(tags=["srm-acquisition"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _require_acquisition_enabled(request: Request) -> None:
    if not _settings(request).acquisition_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hosted acquisition is disabled until a provider passes the verification gates",
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


@router.get("/api/v1/srm/connection", response_model=SrmConnectionResponse)
def connection_status(
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> SrmConnectionResponse:
    connection = get_connection(session, context.user.id)
    return SrmConnectionResponse(
        status=connection.status if connection is not None else "disconnected",
        provider=connection.provider if connection is not None else None,
        netid_hint=netid_hint(connection.verified_netid) if connection is not None else None,
        last_authenticated_at=(
            connection.last_authenticated_at if connection is not None else None
        ),
        last_refreshed_at=(connection.last_refreshed_at if connection is not None else None),
        last_successful_sync=context.user.last_successful_sync_at,
    )


@router.post("/api/v1/srm/auth-attempts", response_model=AuthAttemptResponse)
def start_auth_attempt(
    payload: AuthAttemptStartRequest,
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthAttemptResponse:
    _require_acquisition_enabled(request)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No verified hosted acquisition provider is configured",
    )


@router.post("/api/v1/srm/auth-attempts/{attempt_id}/complete", response_model=AuthAttemptResponse)
def complete_auth_attempt(
    attempt_id: int,
    payload: AuthAttemptCompleteRequest,
    request: Request,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AuthAttemptResponse:
    _require_acquisition_enabled(request)
    try:
        consume_auth_attempt(session, context.user.id, attempt_id)
    except AuthAttemptError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No verified hosted acquisition provider is configured",
    )


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
