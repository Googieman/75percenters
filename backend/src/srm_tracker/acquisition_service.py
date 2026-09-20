"""Owner-scoped connection, challenge, and notification state transitions."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.db_models import (
    AuthAttempt,
    NotificationOutbox,
    PushSubscription,
    SrmConnection,
    SyncJob,
)
from srm_tracker.time import utc_now


class IdentityConflictError(ValueError):
    """Raised when a different SRM identity would be attached to existing history."""


class AuthAttemptError(ValueError):
    """Raised when a challenge is missing, expired, or already consumed."""


def netid_hint(netid: str | None) -> str | None:
    if not netid:
        return None
    if len(netid) <= 2:
        return "*" * len(netid)
    return f"{netid[:2]}{'*' * max(1, len(netid) - 3)}{netid[-1]}"


def get_connection(session: DbSession, user_id: int) -> SrmConnection | None:
    return session.scalar(select(SrmConnection).where(SrmConnection.user_id == user_id))


def create_auth_attempt(
    session: DbSession,
    user_id: int,
    *,
    provider: str,
    netid: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> AuthAttempt:
    """Create an expiring, owner-bound attempt without accepting any password."""
    now = now or utc_now()
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
    )
    if connection is not None and connection.verified_netid.casefold() != netid.casefold():
        raise IdentityConflictError("a different SRM identity cannot replace existing attendance")
    if connection is None:
        connection = SrmConnection(
            user_id=user_id,
            verified_netid=netid,
            provider=provider,
            status="authenticating",
            generation=1,
        )
        session.add(connection)
        session.flush()
    else:
        connection.provider = provider
        connection.status = "authenticating"
    attempt = AuthAttempt(
        user_id=user_id,
        connection_id=connection.id,
        provider=provider,
        status="pending",
        connection_generation=connection.generation,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def consume_auth_attempt(
    session: DbSession,
    user_id: int,
    attempt_id: int,
    *,
    now: datetime | None = None,
) -> AuthAttempt:
    """Atomically make a challenge single-use before provider work begins."""
    now = now or utc_now()
    attempt = session.scalar(
        select(AuthAttempt)
        .where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
        .with_for_update()
    )
    if (
        attempt is None
        or attempt.status != "pending"
        or attempt.consumed_at is not None
        or attempt.expires_at <= now
    ):
        raise AuthAttemptError("authentication attempt is invalid or expired")
    attempt.status = "consumed"
    attempt.consumed_at = now
    session.commit()
    session.refresh(attempt)
    return attempt


def disconnect_connection(session: DbSession, user_id: int, *, now: datetime | None = None) -> None:
    """Cancel owned work and delete active server-side session material."""
    now = now or utc_now()
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
    )
    if connection is None:
        return
    connection.status = "disconnected"
    connection.generation += 1
    connection.encrypted_session_state = None
    connection.last_error_code = "disconnected"
    for job in session.scalars(
        select(SyncJob).where(
            SyncJob.user_id == user_id,
            SyncJob.status.in_(("queued", "claimed")),
        )
    ):
        job.status = "canceled"
        job.claimed_until = None
        job.completed_at = now
        job.result_code = "disconnected"
    for attempt in session.scalars(
        select(AuthAttempt).where(AuthAttempt.user_id == user_id, AuthAttempt.status == "pending")
    ):
        attempt.status = "canceled"
        attempt.consumed_at = now
    session.commit()


def upsert_push_subscription(
    session: DbSession,
    user_id: int,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    now: datetime | None = None,
) -> PushSubscription:
    now = now or utc_now()
    subscription = session.scalar(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint == endpoint,
        )
    )
    if subscription is None:
        subscription = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            last_seen_at=now,
        )
        session.add(subscription)
    else:
        subscription.p256dh = p256dh
        subscription.auth = auth
        subscription.last_seen_at = now
    session.commit()
    session.refresh(subscription)
    return subscription


def queue_reauthentication_notice(
    session: DbSession,
    user_id: int,
    *,
    generation: int,
    now: datetime | None = None,
) -> NotificationOutbox:
    """Create one deduplicated, data-free expiry notification per episode."""
    now = now or utc_now()
    dedupe_key = f"srm-reauth:{user_id}:{generation}"
    notice = session.scalar(
        select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
    )
    if notice is None:
        notice = NotificationOutbox(
            user_id=user_id,
            kind="srm_reauthentication_required",
            dedupe_key=dedupe_key,
            status="pending",
            available_at=now,
        )
        session.add(notice)
        session.commit()
        session.refresh(notice)
    return notice
