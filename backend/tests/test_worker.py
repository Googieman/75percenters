
from srm_tracker.acquisition_provider import HostedSyncResult
from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import NotificationOutbox, SrmConnection, Subject, SyncJob
from srm_tracker.schemas import AttendanceUpload, SubjectUpload
from srm_tracker.sync_jobs import enqueue_sync_job
from srm_tracker.worker import (
    ProviderContractChanged,
    ProviderReauthenticationRequired,
    ProviderTransientFailure,
    SyncWorker,
)


class SuccessfulExecutor:
    def __init__(self, result: HostedSyncResult) -> None:
        self.result = result

    def fetch(self, claim: object) -> HostedSyncResult:
        return self.result


class ReauthExecutor:
    def fetch(self, claim: object) -> HostedSyncResult:
        raise ProviderReauthenticationRequired("challenge required")


def _seed_job(database_session_factory: object) -> tuple[int, int]:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        session.add(
            SrmConnection(
                user_id=user.id,
                verified_netid="AB1234",
                provider="student_portal",
                status="connected",
                generation=1,
                encrypted_session_state=b"opaque",
            )
        )
        session.commit()
        user_id = user.id
    with database_session_factory() as session:  # type: ignore[operator]
        job = enqueue_sync_job(session, user_id, kind="scheduled")
        return user_id, job.id


def test_worker_fetches_outside_transaction_and_uses_fenced_ingestion(
    database_session_factory: object,
) -> None:
    user_id, job_id = _seed_job(database_session_factory)
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
    worker = SyncWorker(
        database_session_factory,
        SuccessfulExecutor(HostedSyncResult(batch=batch, term_context="2026-T1")),
        lease_seconds=120,
    )

    assert worker.run_once() == "succeeded"
    with database_session_factory() as session:  # type: ignore[operator]
        assert session.query(Subject).filter(Subject.user_id == user_id).count() == 1
        saved_job = session.get(SyncJob, job_id)
        assert saved_job is not None and saved_job.status == "succeeded"
        assert saved_job.source_provider == "student_portal"
        assert saved_job.term_context == "2026-T1"


def test_worker_creates_one_reauthentication_notice_and_invalidates_generation(
    database_session_factory: object,
) -> None:
    user_id, job_id = _seed_job(database_session_factory)
    worker = SyncWorker(database_session_factory, ReauthExecutor(), lease_seconds=120)

    assert worker.run_once() == "reauth_required"
    assert worker.run_once() is None
    with database_session_factory() as session:  # type: ignore[operator]
        connection = session.query(SrmConnection).one()
        assert connection.status == "reauth_required"
        assert connection.generation == 2
        assert session.get(SyncJob, job_id).status == "reauth_required"
        assert session.query(NotificationOutbox).filter_by(user_id=user_id).count() == 1


def test_worker_pauses_connection_when_provider_contract_changes(
    database_session_factory: object,
) -> None:
    user_id, job_id = _seed_job(database_session_factory)

    class ChangedExecutor:
        def fetch(self, claim: object) -> HostedSyncResult:
            raise ProviderContractChanged("unexpected source response")

    worker = SyncWorker(database_session_factory, ChangedExecutor(), lease_seconds=120)

    assert worker.run_once() == "source_changed"
    with database_session_factory() as session:  # type: ignore[operator]
        assert session.query(SrmConnection).one().status == "paused"
        assert session.get(SyncJob, job_id).status == "paused"


def test_worker_does_not_persist_provider_exception_text(
    database_session_factory: object,
) -> None:
    _user_id, job_id = _seed_job(database_session_factory)

    class LeakyExecutor:
        def fetch(self, claim: object) -> HostedSyncResult:
            raise ProviderTransientFailure("password=must-not-be-persisted")

    worker = SyncWorker(database_session_factory, LeakyExecutor(), lease_seconds=120)

    assert worker.run_once() == "retrying"
    with database_session_factory() as session:  # type: ignore[operator]
        job = session.get(SyncJob, job_id)
        assert job is not None
        assert job.last_error == "transient provider failure"
        assert "must-not-be-persisted" not in (job.last_error or "")
