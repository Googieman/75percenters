"""Database-backed fixed-window rate limiting."""

from datetime import timedelta
from math import ceil

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from srm_tracker.db_models import RateLimitBucket
from srm_tracker.time import utc_now


class RateLimitExceeded(Exception):
    """Raised after the caller has exhausted the current request window."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = max(1, retry_after)


def consume_rate_limit(
    session: DbSession,
    *,
    action: str,
    key: str,
    max_attempts: int,
    window_seconds: int,
    user_id: int | None = None,
) -> None:
    """Count one attempt atomically and commit the bucket update."""
    now = utc_now()
    bucket = session.scalar(
        select(RateLimitBucket)
        .where(RateLimitBucket.action == action, RateLimitBucket.key == key)
        .with_for_update()
    )
    if bucket is None:
        bucket = RateLimitBucket(
            action=action,
            key=key,
            user_id=user_id,
            window_started_at=now,
            attempts=0,
        )
        session.add(bucket)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            bucket = session.scalar(
                select(RateLimitBucket)
                .where(RateLimitBucket.action == action, RateLimitBucket.key == key)
                .with_for_update()
            )
            if bucket is None:
                raise

    elapsed = now - bucket.window_started_at
    if elapsed >= timedelta(seconds=window_seconds):
        bucket.window_started_at = now
        bucket.attempts = 0

    if bucket.attempts >= max_attempts:
        retry_after = ceil(
            (bucket.window_started_at + timedelta(seconds=window_seconds) - now).total_seconds()
        )
        session.commit()
        raise RateLimitExceeded(retry_after)

    bucket.attempts += 1
    session.commit()
