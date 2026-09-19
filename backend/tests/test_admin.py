import pytest

from srm_tracker.admin import BootstrapError, bootstrap_account
from srm_tracker.security import verify_password


def test_bootstrap_creates_one_argon2_account_and_refuses_second(
    database_session_factory: object,
) -> None:
    factory = database_session_factory
    with factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "Owner@Example.com", "a-very-long-password")
        assert user.email == "owner@example.com"
        assert user.password_hash != "a-very-long-password"
        assert verify_password("a-very-long-password", user.password_hash)
        session.expunge(user)

    with factory() as session, pytest.raises(BootstrapError, match="already exists"):  # type: ignore[operator]
        bootstrap_account(session, "second@example.com", "another-long-password")
