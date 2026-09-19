"""Transactional owner-serialized attendance ingestion."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.db_models import AttendanceSnapshot, ConnectorDevice, Subject, User
from srm_tracker.schemas import AttendanceUpload
from srm_tracker.time import utc_now


class UploadAuthenticationError(ValueError):
    """Raised when a device was revoked between authentication and ingestion."""


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
    """Apply a validated batch atomically, serializing all uploads for its owner."""
    try:
        device = session.scalar(
            select(ConnectorDevice).where(
                ConnectorDevice.id == device_id,
                ConnectorDevice.revoked_at.is_(None),
            )
        )
        if device is None:
            raise UploadAuthenticationError("connector device is revoked or missing")

        user = session.scalar(select(User).where(User.id == device.user_id).with_for_update())
        if user is None:
            raise UploadAuthenticationError("connector owner is missing")
        device = session.scalar(
            select(ConnectorDevice).where(
                ConnectorDevice.id == device_id,
                ConnectorDevice.revoked_at.is_(None),
            ).with_for_update()
        )
        if device is None:
            raise UploadAuthenticationError("connector device is revoked or missing")

        subjects = {
            subject.code: subject
            for subject in session.scalars(select(Subject).where(Subject.user_id == user.id))
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
                    user_id=user.id,
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
        device.last_seen_at = synced_at
        session.commit()
        return UploadResult(
            snapshots_created=snapshots_created,
            subjects_received=len(batch.subjects),
            synced_at=synced_at,
        )
    except Exception:
        session.rollback()
        raise
