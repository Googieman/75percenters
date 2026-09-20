from datetime import timedelta

import pytest

from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import SrmConnection, SyncJob
from srm_tracker.sync_jobs import (
    ConnectionRequiredError,
    SyncTooSoonError,
    claim_due_job,
    enqueue_sync_job,
    recover_abandoned_jobs,
)
from srm_tracker.time import utc_now


def _connected_account(database_session_factory: object) -> tuple[int, int]:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        connection = SrmConnection(
            user_id=user.id,
            verified_netid="AB1234",
            provider="student_portal",
            status="connected",
            generation=4,
            encrypted_session_state=b"encrypted",
        )
        session.add(connection)
        session.commit()
        return user.id, connection.id


def test_enqueue_coalesces_and_claim_fences_a_due_job(database_session_factory: object) -> None:
    user_id, connection_id = _connected_account(database_session_factory)
    with database_session_factory() as session:  # type: ignore[operator]
        first = enqueue_sync_job(session, user_id, kind="manual")
        second = enqueue_sync_job(session, user_id, kind="manual")
        assert first.id == second.id
        claim = claim_due_job(session, lease_seconds=120)

    assert claim is not None
    assert claim.job_id == first.id
    assert claim.fencing_generation == 1
    assert claim.connection_generation == 4
    with database_session_factory() as session:  # type: ignore[operator]
        job = session.get(SyncJob, first.id)
        assert job is not None and job.status == "claimed"
        assert job.connection_id == connection_id
        assert job.claimed_until is not None


def test_claim_recovery_requeues_an_abandoned_lease(database_session_factory: object) -> None:
    user_id, connection_id = _connected_account(database_session_factory)
    with database_session_factory() as session:  # type: ignore[operator]
        job = SyncJob(
            user_id=user_id,
            connection_id=connection_id,
            source_provider="student_portal",
            kind="scheduled",
            status="claimed",
            scheduled_for=utc_now() - timedelta(minutes=2),
            claimed_until=utc_now() - timedelta(seconds=1),
            fencing_generation=3,
            connection_generation=4,
        )
        session.add(job)
        session.commit()
        recovered = recover_abandoned_jobs(session)

    assert recovered == 1
    with database_session_factory() as session:  # type: ignore[operator]
        refreshed = session.get(SyncJob, job.id)
        assert refreshed is not None and refreshed.status == "queued"
        assert refreshed.claimed_until is None


def test_enqueue_requires_connection_and_honors_minimum_interval(
    database_session_factory: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        with pytest.raises(ConnectionRequiredError):
            enqueue_sync_job(session, user.id, kind="manual")
        connection = SrmConnection(
            user_id=user.id,
            verified_netid="AB1234",
            provider="student_portal",
            status="connected",
            generation=1,
            encrypted_session_state=b"encrypted",
        )
        session.add(connection)
        session.commit()
        user_id = user.id
    with database_session_factory() as session:  # type: ignore[operator]
        job = enqueue_sync_job(session, user_id, kind="manual")
        job.status = "succeeded"
        job.completed_at = utc_now()
        session.commit()
        with pytest.raises(SyncTooSoonError):
            enqueue_sync_job(session, user_id, kind="manual")
