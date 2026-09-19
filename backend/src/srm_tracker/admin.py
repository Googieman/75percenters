"""Administrative bootstrap command for the single personal account."""

import argparse
import getpass

from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from srm_tracker.config import get_settings
from srm_tracker.db import create_engine_from_settings, session_factory_for_engine
from srm_tracker.db_models import User
from srm_tracker.security import hash_password


class BootstrapError(ValueError):
    """Raised when the one-account bootstrap contract cannot be satisfied."""


def normalize_email(email: str) -> str:
    """Normalize the account identifier without accepting blank credentials."""
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized or " " in normalized:
        raise BootstrapError("a valid email address is required")
    return normalized


def bootstrap_account(session: DbSession, email: str, password: str) -> User:
    """Create the first account and refuse every subsequent bootstrap attempt."""
    if len(password) < 12:
        raise BootstrapError("password must contain at least 12 characters")

    session.execute(text("SELECT pg_advisory_xact_lock(872341)"))
    if session.scalar(select(User.id).limit(1)) is not None:
        raise BootstrapError("bootstrap account already exists")

    user = User(email=normalize_email(email), password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _run_bootstrap() -> None:
    settings = get_settings()
    engine = create_engine_from_settings(settings)
    factory = session_factory_for_engine(engine)
    try:
        email = input("Account email: ")
        password = getpass.getpass("Account password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise BootstrapError("password confirmation does not match")
        with factory() as session:
            bootstrap_account(session, email, password)
        print("Bootstrap account created.")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="SRM Attendance Tracker administration")
    parser.add_argument("command", choices=("bootstrap",))
    args = parser.parse_args()
    if args.command == "bootstrap":
        _run_bootstrap()


if __name__ == "__main__":
    main()
