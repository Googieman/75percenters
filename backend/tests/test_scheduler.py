from datetime import timedelta

from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import SrmConnection, SyncJob, User
from srm_tracker.sync_jobs import enqueue_due_scheduled_jobs
from srm_tracker.time import utc_now


def test_scheduler_queues_each_due_connection_once(database_session_factory: object) -> None:
    now = utc_now()
    with database_session_factory() as session:  # type: ignore[operator]
        due_user = bootstrap_account(session, "due@example.com", "a-very-long-password")
        future_user = User(email="future@example.com", password_hash="test-hash")
        session.add(future_user)
        session.flush()
        session.add_all(
            [
                SrmConnection(
                    user_id=due_user.id,
                    verified_netid="DUE123",
                    provider="campusweb_student_portal",
                    status="connected",
                    encrypted_session_state=b"opaque",
                    next_scheduled_refresh=now - timedelta(seconds=1),
                ),
                SrmConnection(
                    user_id=future_user.id,
                    verified_netid="FUTURE123",
                    provider="campusweb_student_portal",
                    status="connected",
                    encrypted_session_state=b"opaque",
                    next_scheduled_refresh=now + timedelta(minutes=10),
                ),
            ]
        )
        session.commit()

        assert enqueue_due_scheduled_jobs(session, now=now) == 1
        assert enqueue_due_scheduled_jobs(session, now=now) == 0

        jobs = session.query(SyncJob).all()
        assert len(jobs) == 1
        assert jobs[0].kind == "scheduled"
        assert jobs[0].source_provider == "campusweb_student_portal"


def test_scheduler_does_not_queue_disconnected_or_incomplete_connections(
    database_session_factory: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "offline@example.com", "a-very-long-password")
        session.add(
            SrmConnection(
                user_id=user.id,
                verified_netid="OFF123",
                provider="campusweb_student_portal",
                status="disconnected",
                encrypted_session_state=None,
                next_scheduled_refresh=utc_now() - timedelta(hours=1),
            )
        )
        session.commit()

        assert enqueue_due_scheduled_jobs(session) == 0
        assert session.query(SyncJob).count() == 0
