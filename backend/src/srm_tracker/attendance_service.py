"""Transactional, source-independent attendance ingestion."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.db_models import (
    AttendanceSnapshot,
    ConnectorDevice,
    SrmConnection,
    Subject,
    SyncJob,
    User,
)
from srm_tracker.schemas import AttendanceUpload
from srm_tracker.time import utc_now


class UploadAuthenticationError(ValueError):
    """Raised when a connector was revoked between authentication and ingestion."""


class StaleAcquisitionError(ValueError):
    """Raised when a disconnected, expired, or superseded hosted job tries to commit."""


@dataclass(frozen=True, slots=True)
class UploadResult:
    snapshots_created: int
    subjects_received: int
    synced_at: datetime


def process_upload(
    session: DbSession,
    device_id: int,
    batch: AttendanceUpload,
) -> UploadResult:
    """Preserve the connector API while routing through shared ingestion logic."""
    device = session.scalar(select(ConnectorDevice).where(ConnectorDevice.id == device_id))
    if device is None:
        raise UploadAuthenticationError("connector device is revoked or missing")
    return process_acquisition_ingestion(
        session,
        device.user_id,
        batch,
        source="connector",
        connector_device_id=device_id,
    )


def process_acquisition_ingestion(
    session: DbSession,
    owner_id: int,
    batch: AttendanceUpload,
    *,
    source: str,
    connector_device_id: int | None = None,
    connection_id: int | None = None,
    job_id: int | None = None,
    expected_connection_generation: int | None = None,
    expected_fencing_generation: int | None = None,
    term_context: str | None = None,
    expected_term_context: str | None = None,
    commit: bool = True,
) -> UploadResult:
    """Apply any verified source's batch atomically for one owner.

    The owner is resolved by trusted server-side records. Client payloads contain only
    validated attendance records and never select an owner or source identity.
    """
    if source not in {"connector", "hosted"}:
        raise ValueError("unsupported ingestion source")
    try:
        user = session.scalar(select(User).where(User.id == owner_id).with_for_update())
        if user is None:
            raise UploadAuthenticationError("attendance owner is missing")

        device = None
        if connector_device_id is not None:
            device = session.scalar(
                select(ConnectorDevice)
                .where(
                    ConnectorDevice.id == connector_device_id,
                    ConnectorDevice.user_id == owner_id,
                    ConnectorDevice.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if device is None:
                raise UploadAuthenticationError("connector device is revoked or missing")

        connection = None
        if connection_id is not None:
            connection = session.scalar(
                select(SrmConnection)
                .where(SrmConnection.id == connection_id, SrmConnection.user_id == owner_id)
                .with_for_update()
            )
            if connection is None:
                raise StaleAcquisitionError("SRM connection is missing")
            if (
                expected_connection_generation is not None
                and connection.generation != expected_connection_generation
            ):
                raise StaleAcquisitionError("SRM connection was superseded")
            if (
                expected_term_context is not None
                and connection.term_context != expected_term_context
            ):
                raise StaleAcquisitionError("SRM connection context was superseded")

        job = None
        if job_id is not None:
            job = session.scalar(
                select(SyncJob)
                .where(SyncJob.id == job_id, SyncJob.user_id == owner_id)
                .with_for_update()
            )
            now = utc_now()
            if (
                job is None
                or job.status != "claimed"
                or job.claimed_until is None
                or job.claimed_until <= now
                or expected_fencing_generation is None
                or job.fencing_generation != expected_fencing_generation
            ):
                raise StaleAcquisitionError("sync job lease is no longer valid")
            if connection_id != job.connection_id:
                raise StaleAcquisitionError("sync job connection does not match")
            if (
                expected_connection_generation is not None
                and job.connection_generation != expected_connection_generation
            ):
                raise StaleAcquisitionError("sync job connection generation is stale")

        subjects = {
            subject.code: subject
            for subject in session.scalars(select(Subject).where(Subject.user_id == owner_id))
        }
        snapshots_created = 0
        for item in batch.subjects:
            subject = subjects.get(item.code)
            changed = (
                subject is None
                or subject.total_hours != item.total_hours
                or subject.attended_hours != item.attended_hours
                or subject.absent_hours != item.absent_hours
            )
            if subject is None:
                subject = Subject(
                    user_id=owner_id,
                    code=item.code,
                    name=item.subject,
                    total_hours=item.total_hours,
                    attended_hours=item.attended_hours,
                    absent_hours=item.absent_hours,
                    source_percentage=item.source_percentage,
                )
                session.add(subject)
                session.flush()
                subjects[item.code] = subject
            else:
                subject.name = item.subject
                subject.total_hours = item.total_hours
                subject.attended_hours = item.attended_hours
                subject.absent_hours = item.absent_hours
                subject.source_percentage = item.source_percentage

            if changed:
                session.add(
                    AttendanceSnapshot(
                        subject_id=subject.id,
                        total_hours=item.total_hours,
                        attended_hours=item.attended_hours,
                        absent_hours=item.absent_hours,
                        source_percentage=item.source_percentage,
                    )
                )
                snapshots_created += 1

        synced_at = utc_now()
        user.last_successful_sync_at = synced_at
        if device is not None:
            device.last_seen_at = synced_at
        if connection is not None:
            if term_context is not None:
                connection.term_context = term_context
            connection.last_refreshed_at = synced_at
            connection.status = "connected"
            connection.last_error_code = None
        if job is not None:
            if connection is not None:
                job.source_provider = connection.provider
            if term_context is not None:
                job.term_context = term_context
            job.status = "succeeded"
            job.result_code = "updated" if snapshots_created else "unchanged"
            job.last_error = None
            job.completed_at = synced_at
            job.claimed_until = None
        if commit:
            session.commit()
        return UploadResult(
            snapshots_created=snapshots_created,
            subjects_received=len(batch.subjects),
            synced_at=synced_at,
        )
    except Exception:
        session.rollback()
        raise
