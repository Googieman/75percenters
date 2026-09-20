"""Owner-scoped connection, challenge, and notification state transitions."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.acquisition_crypto import SessionCipher, SessionKeyring
from srm_tracker.acquisition_provider import ProviderSession
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
    if (
        connection is not None
        and connection.verified_netid is not None
        and connection.verified_netid.casefold() != netid.casefold()
    ):
        raise IdentityConflictError("a different SRM identity cannot replace existing attendance")
    if connection is None:
        connection = SrmConnection(
            user_id=user_id,
            verified_netid=None,
            pending_netid=netid,
            provider=provider,
            status="authenticating",
            generation=1,
        )
        session.add(connection)
        session.flush()
    else:
        connection.provider = provider
        connection.status = "authenticating"
        connection.pending_netid = netid
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


def fail_auth_attempt(
    session: DbSession,
    user_id: int,
    attempt_id: int,
    *,
    status: str,
    message: str,
    now: datetime | None = None,
) -> AuthAttempt:
    """Record only a safe provider outcome after transient input is discarded."""
    now = now or utc_now()
    attempt = session.scalar(
        select(AuthAttempt).where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
    )
    if attempt is None:
        raise AuthAttemptError("authentication attempt is unavailable")
    connection = (
        session.scalar(
            select(SrmConnection)
            .where(SrmConnection.id == attempt.connection_id)
            .with_for_update()
        )
        if attempt.connection_id is not None
        else None
    )
    attempt = session.scalar(
        select(AuthAttempt)
        .where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
        .with_for_update()
    )
    if attempt is None:
        raise AuthAttemptError("authentication attempt is unavailable")
    attempt.status = status
    attempt.display_message = message[:255]
    attempt.encrypted_state = None
    attempt.state_key_version = None
    attempt.updated_at = now
    if connection is not None and connection.status == "authenticating":
        if connection.encrypted_session_state is not None and connection.verified_netid is not None:
            connection.status = "connected"
            connection.pending_netid = None
            connection.last_error_code = "authentication_failed"
        else:
            connection.status = "disconnected"
            connection.pending_netid = None
            connection.last_error_code = "authentication_failed"
    session.commit()
    session.refresh(attempt)
    return attempt


def promote_authenticated_session(
    session: DbSession,
    user_id: int,
    attempt_id: int,
    provider_session: ProviderSession,
    *,
    provider: str,
    cipher: SessionCipher | SessionKeyring,
    now: datetime | None = None,
) -> tuple[AuthAttempt, SyncJob]:
    """Atomically promote provider evidence and queue the first refresh."""
    now = now or utc_now()
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
    )
    attempt = session.scalar(
        select(AuthAttempt)
        .where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
        .with_for_update()
    )
    if (
        attempt is None
        or connection is None
        or attempt.connection_id != connection.id
        or attempt.status != "consumed"
        or attempt.expires_at <= now
    ):
        raise AuthAttemptError("authentication attempt is invalid or expired")
    if connection.pending_netid is None or (
        connection.pending_netid.casefold() != provider_session.verified_netid.casefold()
    ):
        raise IdentityConflictError("provider identity did not match the requested account")
    if connection.verified_netid is not None and (
        connection.verified_netid.casefold() != provider_session.verified_netid.casefold()
    ):
        raise IdentityConflictError("provider identity cannot replace existing attendance")

    connection.generation += 1
    connection.provider = provider
    connection.verified_netid = provider_session.verified_netid
    connection.pending_netid = None
    connection.term_context = provider_session.term_context
    connection.status = "connected"
    connection.last_authenticated_at = now
    connection.last_error_code = None
    cancel_pending_notifications(session, user_id)
    connection.encrypted_session_state = cipher.encrypt(
        provider_session.state,
        owner_id=user_id,
        provider=provider,
        generation=connection.generation,
    )
    connection.session_key_version = cipher.key_version

    for job in session.scalars(
        select(SyncJob).where(
            SyncJob.connection_id == connection.id,
            SyncJob.status.in_(("queued", "claimed")),
        )
    ):
        job.status = "canceled"
        job.claimed_until = None
        job.completed_at = now
        job.result_code = "superseded"
    for other in session.scalars(
        select(AuthAttempt).where(
            AuthAttempt.user_id == user_id,
            AuthAttempt.id != attempt.id,
            AuthAttempt.status == "pending",
        )
    ):
        other.status = "canceled"
        other.consumed_at = now
        other.encrypted_state = None
        other.state_key_version = None

    attempt.status = "succeeded"
    attempt.display_message = "CampusWeb connected"
    attempt.encrypted_state = None
    attempt.state_key_version = None
    attempt.updated_at = now
    job = SyncJob(
        user_id=user_id,
        connection_id=connection.id,
        source_provider=provider,
        term_context=provider_session.term_context,
        kind="initial",
        status="queued",
        scheduled_for=now,
        connection_generation=connection.generation,
    )
    session.add(job)
    session.commit()
    session.refresh(attempt)
    session.refresh(job)
    return attempt, job


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
        select(AuthAttempt).where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
    )
    connection = (
        session.scalar(
            select(SrmConnection)
            .where(SrmConnection.id == attempt.connection_id)
            .with_for_update()
        )
        if attempt is not None and attempt.connection_id is not None
        else None
    )
    attempt = session.scalar(
        select(AuthAttempt)
        .where(AuthAttempt.id == attempt_id, AuthAttempt.user_id == user_id)
        .with_for_update()
    )
    if (
        attempt is None
        or connection is None
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


def cleanup_expired_auth_attempts(
    session: DbSession, *, now: datetime | None = None
) -> int:
    """Remove challenge ciphertext after its ten-minute validity window."""
    now = now or utc_now()
    attempts = session.scalars(
        select(AuthAttempt)
        .where(
            AuthAttempt.expires_at <= now,
            AuthAttempt.status.in_(("pending", "consumed")),
            AuthAttempt.encrypted_state.is_not(None),
        )
        .with_for_update(skip_locked=True)
    ).all()
    for attempt in attempts:
        attempt.status = "expired"
        attempt.encrypted_state = None
        attempt.state_key_version = None
        attempt.consumed_at = attempt.consumed_at or now
        if attempt.connection_id is not None:
            connection = session.scalar(
                select(SrmConnection)
                .where(SrmConnection.id == attempt.connection_id)
                .with_for_update()
            )
            if connection is not None and connection.status == "authenticating":
                connection.status = "disconnected"
                connection.pending_netid = None
                connection.last_error_code = "auth_expired"
    session.commit()
    return len(attempts)


def disconnect_connection(session: DbSession, user_id: int, *, now: datetime | None = None) -> None:
    """Cancel owned work and delete active server-side session material."""
    now = now or utc_now()
    connection = session.scalar(
        select(SrmConnection).where(SrmConnection.user_id == user_id).with_for_update()
    )
    if connection is None:
        return
    cancel_pending_notifications(session, user_id)
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
        attempt.encrypted_state = None
        attempt.state_key_version = None
    session.commit()


def cancel_pending_notifications(session: DbSession, user_id: int) -> None:
    """Cancel unsent notices made obsolete by a fresh connection or disconnect."""
    notices = session.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.user_id == user_id,
            NotificationOutbox.status.in_(("pending", "dispatching")),
        )
    ).all()
    for notice in notices:
        notice.status = "canceled"
        for delivery in notice.deliveries:
            if delivery.status == "pending":
                delivery.status = "canceled"


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
