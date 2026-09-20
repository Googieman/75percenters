"""Background worker orchestration with provider injection and durable fencing."""

from datetime import timedelta
from threading import Event
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.acquisition_crypto import SessionKeyring
from srm_tracker.acquisition_provider import HostedSyncResult
from srm_tracker.acquisition_service import (
    cleanup_expired_auth_attempts,
    queue_reauthentication_notice,
)
from srm_tracker.attendance_service import StaleAcquisitionError, process_acquisition_ingestion
from srm_tracker.db_models import SrmConnection, SyncJob
from srm_tracker.sync_jobs import (
    JobClaim,
    claim_due_job,
    enqueue_due_scheduled_jobs,
    recover_abandoned_jobs,
)
from srm_tracker.time import utc_now


class ProviderReauthenticationRequired(RuntimeError):
    """The user must complete a fresh provider challenge."""


class ProviderContractChanged(RuntimeError):
    """The provider response changed and collection must fail closed."""


class ProviderTransientFailure(RuntimeError):
    """The provider can be retried without changing account state."""

    def __init__(self, message: str = "transient provider failure", retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


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
        scheduled_interval_minutes: int = 60,
        cipher: SessionKeyring | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.scheduled_interval_minutes = scheduled_interval_minutes
        self.cipher = cipher

    def run_once(self) -> str | None:
        with self.session_factory() as session:
            cleanup_expired_auth_attempts(session)
            recover_abandoned_jobs(session)
            enqueue_due_scheduled_jobs(
                session,
                interval_minutes=self.scheduled_interval_minutes,
            )
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
            self._schedule_retry(claim, retry_after=error.retry_after)
            return "retrying"

        if result.session_state is not None and self.cipher is None:
            self._schedule_retry(claim)
            return "retrying"

        with self.session_factory() as session:
            try:
                if claim.term_context is not None and claim.term_context != result.term_context:
                    raise ProviderContractChanged("term context changed")
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
                    expected_term_context=claim.term_context,
                    commit=False,
                )
                connection = session.scalar(
                    select(SrmConnection).where(SrmConnection.id == claim.connection_id)
                )
                if connection is None:
                    raise StaleAcquisitionError("connection was superseded during fetch")
                if result.session_state is not None:
                    assert self.cipher is not None
                    connection.encrypted_session_state = self.cipher.encrypt(
                        result.session_state,
                        owner_id=connection.user_id,
                        provider=connection.provider,
                        generation=connection.generation,
                    )
                    connection.session_key_version = self.cipher.key_version
                connection.next_scheduled_refresh = utc_now() + timedelta(
                    minutes=self.scheduled_interval_minutes
                )
                session.commit()
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
                or job.status != "claimed"
                or connection.generation != claim.connection_generation
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
                or job.status != "claimed"
                or connection.generation != claim.connection_generation
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

    def _schedule_retry(self, claim: JobClaim, *, retry_after: int | None = None) -> None:
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
                or job.status != "claimed"
                or connection.generation != claim.connection_generation
            ):
                session.rollback()
                return
            now = utc_now()
            if job.attempt_count >= 3:
                job.status = "failed"
                job.claimed_until = None
                job.result_code = "retry_exhausted"
                job.last_error = "transient provider failure"
                job.completed_at = now
                connection.next_scheduled_refresh = now + timedelta(
                    minutes=self.scheduled_interval_minutes
                )
                session.commit()
                return
            delay_minutes = 5 if job.attempt_count == 1 else 15
            retry_seconds = max(delay_minutes * 60, retry_after or 0)
            retry_at = now + timedelta(seconds=retry_seconds)
            job.status = "queued"
            job.claimed_until = None
            job.retry_at = retry_at
            job.scheduled_for = retry_at
            job.result_code = "transient_failure"
            job.last_error = "transient provider failure"
            session.commit()
