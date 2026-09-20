"""Background worker orchestration with provider injection and durable fencing."""

from datetime import timedelta
from threading import Event
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.acquisition_provider import HostedSyncResult
from srm_tracker.acquisition_service import queue_reauthentication_notice
from srm_tracker.attendance_service import StaleAcquisitionError, process_acquisition_ingestion
from srm_tracker.db_models import SrmConnection, SyncJob
from srm_tracker.sync_jobs import (
    JobClaim,
    claim_due_job,
    recover_abandoned_jobs,
)
from srm_tracker.time import utc_now


class ProviderReauthenticationRequired(RuntimeError):
    """The user must complete a fresh provider challenge."""


class ProviderContractChanged(RuntimeError):
    """The provider response changed and collection must fail closed."""


class ProviderTransientFailure(RuntimeError):
    """The provider can be retried without changing account state."""


class SyncExecutor(Protocol):
    def fetch(self, claim: JobClaim) -> HostedSyncResult:
        """Perform network work after the claim transaction has committed."""


class SyncWorker:
    def __init__(
        self,
        session_factory: sessionmaker[DbSession],
        executor: SyncExecutor,
        *,
        lease_seconds: int = 300,
        poll_interval_seconds: int = 30,
    ) -> None:
        self.session_factory = session_factory
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def run_once(self) -> str | None:
        with self.session_factory() as session:
            recover_abandoned_jobs(session)
        with self.session_factory() as session:
            claim = claim_due_job(session, lease_seconds=self.lease_seconds)
        if claim is None:
            return None

        try:
            result = self.executor.fetch(claim)
        except ProviderReauthenticationRequired:
            self._mark_reauthentication_required(claim)
            return "reauth_required"
        except ProviderContractChanged:
            self._mark_source_changed(claim)
            return "source_changed"
        except ProviderTransientFailure as error:
            self._schedule_retry(claim, str(error))
            return "retrying"

        with self.session_factory() as session:
            try:
                connection = session.scalar(
                    select(SrmConnection)
                    .where(SrmConnection.id == claim.connection_id)
                    .with_for_update()
                )
                if connection is None or connection.generation != claim.connection_generation:
                    raise StaleAcquisitionError("connection was superseded during fetch")
                if (
                    connection.term_context is not None
                    and connection.term_context != result.term_context
                ):
                    raise ProviderContractChanged("term context changed")
                connection.term_context = result.term_context
                process_acquisition_ingestion(
                    session,
                    claim.user_id,
                    result.batch,
                    source="hosted",
                    connection_id=claim.connection_id,
                    job_id=claim.job_id,
                    expected_connection_generation=claim.connection_generation,
                    expected_fencing_generation=claim.fencing_generation,
                    term_context=result.term_context,
                )
            except ProviderContractChanged:
                session.rollback()
                self._mark_source_changed(claim)
                return "source_changed"
            except StaleAcquisitionError:
                session.rollback()
                return "stale"
        return "succeeded"

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            self.run_once()
            stop_event.wait(self.poll_interval_seconds)

    def _mark_reauthentication_required(self, claim: JobClaim) -> None:
        with self.session_factory() as session:
            connection = session.scalar(
                select(SrmConnection)
                .where(SrmConnection.id == claim.connection_id)
                .with_for_update()
            )
            job = session.scalar(
                select(SyncJob).where(SyncJob.id == claim.job_id).with_for_update()
            )
            if (
                connection is None
                or job is None
                or job.fencing_generation != claim.fencing_generation
            ):
                session.rollback()
                return
            connection.status = "reauth_required"
            connection.generation += 1
            connection.encrypted_session_state = None
            job.status = "reauth_required"
            job.claimed_until = None
            job.result_code = "reauth_required"
            job.completed_at = utc_now()
            queue_reauthentication_notice(session, claim.user_id, generation=connection.generation)
            session.commit()

    def _mark_source_changed(self, claim: JobClaim) -> None:
        with self.session_factory() as session:
            connection = session.scalar(
                select(SrmConnection)
                .where(SrmConnection.id == claim.connection_id)
                .with_for_update()
            )
            job = session.scalar(
                select(SyncJob).where(SyncJob.id == claim.job_id).with_for_update()
            )
            if (
                connection is None
                or job is None
                or job.fencing_generation != claim.fencing_generation
            ):
                session.rollback()
                return
            connection.status = "paused"
            connection.generation += 1
            connection.encrypted_session_state = None
            connection.last_error_code = "source_changed"
            job.status = "paused"
            job.claimed_until = None
            job.result_code = "source_changed"
            job.completed_at = utc_now()
            session.commit()

    def _schedule_retry(self, claim: JobClaim, error_message: str) -> None:
        with self.session_factory() as session:
            job = session.scalar(
                select(SyncJob).where(SyncJob.id == claim.job_id).with_for_update()
            )
            if job is None or job.fencing_generation != claim.fencing_generation:
                session.rollback()
                return
            delay_minutes = 5 if job.attempt_count <= 1 else 15 if job.attempt_count == 2 else 60
            retry_at = utc_now() + timedelta(minutes=delay_minutes)
            job.status = "queued"
            job.claimed_until = None
            job.retry_at = retry_at
            job.scheduled_for = retry_at
            job.result_code = "transient_failure"
            job.last_error = error_message[:255]
            session.commit()
