from datetime import timedelta

import pytest

from srm_tracker.admin import bootstrap_account
from srm_tracker.attendance_service import (
    StaleAcquisitionError,
    process_acquisition_ingestion,
)
from srm_tracker.db_models import SrmConnection, SyncJob, User
from srm_tracker.schemas import AttendanceUpload, SubjectUpload
from srm_tracker.time import utc_now


def test_hosted_ingestion_updates_common_state_and_completes_its_fenced_job(
    database_session_factory: object,
) -> None:
    batch = AttendanceUpload(
        subjects=[
            SubjectUpload(
                code="CSE1",
                subject="Algorithms",
                total_hours=10,
                attended_hours=8,
                absent_hours=2,
                source_percentage="80",
            )
        ]
    )
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        connection = SrmConnection(
            user_id=user.id,
            verified_netid="AB1234",
            provider="student_portal",
            status="connected",
            generation=2,
        )
        session.add(connection)
        session.flush()
        job = SyncJob(
            user_id=user.id,
            connection_id=connection.id,
            source_provider="student_portal",
            status="claimed",
            scheduled_for=utc_now(),
            claimed_until=utc_now() + timedelta(minutes=2),
            fencing_generation=7,
            connection_generation=2,
        )
        session.add(job)
        session.commit()
        connection_id = connection.id
        job_id = job.id
        user_id = user.id

    with database_session_factory() as session:  # type: ignore[operator]
        result = process_acquisition_ingestion(
            session,
            user_id,
            batch,
            source="hosted",
            connection_id=connection_id,
            job_id=job_id,
            expected_connection_generation=2,
            expected_fencing_generation=7,
        )
        assert result.snapshots_created == 1

    with database_session_factory() as session:  # type: ignore[operator]
        refreshed_user = session.get(User, user_id)
        refreshed_job = session.get(SyncJob, job_id)
        assert refreshed_user is not None and refreshed_user.last_successful_sync_at is not None
        assert refreshed_job is not None and refreshed_job.status == "succeeded"


def test_hosted_ingestion_rejects_a_superseded_connection_before_writing(
    database_session_factory: object,
) -> None:
    batch = AttendanceUpload(
        subjects=[
            SubjectUpload(
                code="CSE1",
                subject="Algorithms",
                total_hours=1,
                attended_hours=1,
                absent_hours=0,
                source_percentage="100",
            )
        ]
    )
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        connection = SrmConnection(
            user_id=user.id,
            verified_netid="AB1234",
            provider="student_portal",
            status="connected",
            generation=3,
        )
        session.add(connection)
        session.commit()
        user_id = user.id
        connection_id = connection.id

    with database_session_factory() as session, pytest.raises(StaleAcquisitionError):  # type: ignore[operator]
        process_acquisition_ingestion(
            session,
            user_id,
            batch,
            source="hosted",
            connection_id=connection_id,
            expected_connection_generation=2,
        )
