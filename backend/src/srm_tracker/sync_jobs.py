"""Durable sync-job enqueueing, leases, fencing, and retry timing."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.db_models import SrmConnection, SyncJob, User
from srm_tracker.time import utc_now


class ConnectionRequiredError(ValueError):
    """Raised when a refresh is requested without a connected SRM identity."""


class SyncTooSoonError(ValueError):
    """Raised when a refresh would violate the minimum manual-refresh interval."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("a refresh was completed too recently")


def enqueue_due_scheduled_jobs(
    session: DbSession,
    *,
    interval_minutes: int = 60,
    now: datetime | None = None,
) -> int:
    """Queue one hourly refresh for every connected, due account."""
    now = now or utc_now()
    due_user_ids = session.scalars(
        select(SrmConnection.user_id)
        .where(
            SrmConnection.status == "connected",
            SrmConnection.encrypted_session_state.is_not(None),
            or_(
                SrmConnection.next_scheduled_refresh.is_(None),
                SrmConnection.next_scheduled_refresh <= now,
            ),
        )
        .order_by(SrmConnection.user_id)
    ).all()
    queued = 0
    for user_id in due_user_ids:
        try:
            job = enqueue_sync_job(session, user_id, kind="scheduled", now=now)
        except ConnectionRequiredError:
            continue
        connection = session.scalar(
            select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
        )
        if connection is None:
            continue
        connection.next_scheduled_refresh = now + timedelta(minutes=interval_minutes)
        session.commit()
        if job.kind == "scheduled":
            queued += 1
    return queued


@dataclass(frozen=True, slots=True)
class JobClaim:
    job_id: int
    user_id: int
    connection_id: int
    connection_generation: int
    fencing_generation: int
    term_context: str | None


def enqueue_sync_job(
    session: DbSession,
    user_id: int,
    *,
    kind: str,
    minimum_interval_minutes: int = 5,
    now: datetime | None = None,
) -> SyncJob:
    """Queue one owned refresh and coalesce any already-running refresh."""
    now = now or utc_now()
    user = session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ConnectionRequiredError("account is missing")
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
    )
    if (
        connection is None
        or connection.status != "connected"
        or connection.encrypted_session_state is None
    ):
        raise ConnectionRequiredError("connect SRM before refreshing")

    active_job = session.scalar(
        select(SyncJob)
        .where(
            SyncJob.user_id == user_id,
            SyncJob.connection_id == connection.id,
            SyncJob.status.in_(("queued", "claimed")),
        )
        .order_by(SyncJob.id.desc())
    )
    if active_job is not None:
        return active_job

    latest_completion = user.last_successful_sync_at
    latest_job = session.scalar(
        select(SyncJob.completed_at)
        .where(SyncJob.user_id == user_id, SyncJob.status == "succeeded")
        .order_by(SyncJob.completed_at.desc())
    )
    if latest_completion is None or (latest_job is not None and latest_job > latest_completion):
        latest_completion = latest_job
    if kind == "manual" and latest_completion is not None:
        elapsed = (now - latest_completion).total_seconds()
        minimum_seconds = minimum_interval_minutes * 60
        if elapsed < minimum_seconds:
            raise SyncTooSoonError(max(1, int(minimum_seconds - elapsed)))

    job = SyncJob(
        user_id=user_id,
        connection_id=connection.id,
        source_provider=connection.provider,
        term_context=connection.term_context,
        kind=kind,
        status="queued",
        scheduled_for=now,
        connection_generation=connection.generation,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_due_job(
    session: DbSession,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> JobClaim | None:
    """Claim one due job with a fencing generation that stale workers cannot reuse."""
    now = now or utc_now()
    job = session.scalar(
        select(SyncJob)
        .where(
            SyncJob.status == "queued",
            SyncJob.scheduled_for <= now,
            or_(SyncJob.retry_at.is_(None), SyncJob.retry_at <= now),
        )
        .order_by(SyncJob.scheduled_for, SyncJob.id)
        .with_for_update(skip_locked=True)
    )
    if job is None or job.connection_id is None:
        session.commit()
        return None
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.id == job.connection_id).with_for_update()
    )
    if connection is None or connection.status != "connected":
        job.status = "reauth_required"
        job.result_code = "connection_required"
        job.completed_at = now
        session.commit()
        return None
    job.status = "claimed"
    job.claimed_until = now + timedelta(seconds=lease_seconds)
    job.fencing_generation += 1
    job.attempt_count += 1
    job.connection_generation = connection.generation
    job.retry_at = None
    session.commit()
    return JobClaim(
        job_id=job.id,
        user_id=job.user_id,
        connection_id=connection.id,
        connection_generation=connection.generation,
        fencing_generation=job.fencing_generation,
        term_context=connection.term_context,
    )


def recover_abandoned_jobs(session: DbSession, *, now: datetime | None = None) -> int:
    """Make expired claims eligible again without reusing their old fence."""
    now = now or utc_now()
    jobs = session.scalars(
        select(SyncJob).where(
            SyncJob.status == "claimed",
            SyncJob.claimed_until.is_not(None),
            SyncJob.claimed_until <= now,
        ).with_for_update(skip_locked=True)
    ).all()
    for job in jobs:
        job.status = "queued"
        job.claimed_until = None
        job.scheduled_for = now
        job.last_error = "worker lease expired"
    session.commit()
    return len(jobs)
