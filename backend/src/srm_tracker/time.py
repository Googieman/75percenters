"""Time helpers shared by persistence and security services."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC timestamp for values whose expiry is app-computed."""
    return datetime.now(UTC)
