import base64
from datetime import timedelta

from srm_tracker.acquisition_crypto import SessionCipher
from srm_tracker.acquisition_service import cleanup_expired_auth_attempts
from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import AuthAttempt, SrmConnection
from srm_tracker.session_store import store_attempt_state
from srm_tracker.time import utc_now


def test_expired_attempt_cleanup_removes_challenge_ciphertext(
    database_session_factory: object,
) -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    cipher = SessionCipher.from_base64(key)
    now = utc_now()
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "expired@example.com", "a-very-long-password")
        connection = SrmConnection(
            user_id=user.id,
            provider="campusweb_student_portal",
            status="authenticating",
            pending_netid="AB1234",
        )
        session.add(connection)
        session.flush()
        attempt = AuthAttempt(
            user_id=user.id,
            connection_id=connection.id,
            provider="campusweb_student_portal",
            status="pending",
            connection_generation=connection.generation,
            expires_at=now - timedelta(seconds=1),
        )
        session.add(attempt)
        session.flush()
        store_attempt_state(attempt, cipher, b"challenge")
        session.commit()

        assert cleanup_expired_auth_attempts(session, now=now) == 1
        assert attempt.status == "expired"
        assert attempt.encrypted_state is None
        assert connection.status == "disconnected"
        assert connection.pending_netid is None
