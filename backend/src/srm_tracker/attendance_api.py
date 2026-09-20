"""Protected attendance reads, settings, history, and connector ingestion."""

import base64
import binascii
from decimal import Decimal
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from srm_tracker.attendance.calculations import AttendanceGuidance, calculate_attendance_guidance
from srm_tracker.attendance_service import UploadAuthenticationError, process_upload
from srm_tracker.auth import AuthContext, get_current_auth, require_csrf
from srm_tracker.config import Settings
from srm_tracker.db import get_request_db
from srm_tracker.db_models import AttendanceSnapshot, Subject
from srm_tracker.pairing import ConnectorContext, get_connector_context
from srm_tracker.schemas import (
    AttendanceResponse,
    AttendanceUpload,
    GuidanceResponse,
    HistoryItem,
    HistoryResponse,
    SettingsResponse,
    SettingsUpdate,
    SubjectAttendanceResponse,
    UploadResponse,
)

router = APIRouter(tags=["attendance"])


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _guidance(guidance: AttendanceGuidance) -> GuidanceResponse:
    return GuidanceResponse(
        current_percentage=(
            float(guidance.current_percentage) if guidance.current_percentage is not None else None
        ),
        additional_attended_hours=guidance.additional_attended_hours,
        additional_absences_allowed=guidance.additional_absences_allowed,
        target_reachable=guidance.target_reachable,
    )


def _cursor(value: int) -> str:
    return base64.urlsafe_b64encode(str(value).encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> int:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("ascii")
        cursor = int(decoded)
    except (ValueError, UnicodeDecodeError, binascii.Error) as error:
        raise HTTPException(status_code=400, detail="Invalid history cursor") from error
    if cursor <= 0:
        raise HTTPException(status_code=400, detail="Invalid history cursor")
    return cursor


def _subject_response(subject: Subject, target: Decimal) -> SubjectAttendanceResponse:
    guidance = calculate_attendance_guidance(
        subject.attended_hours,
        subject.total_hours,
        target,
    )
    return SubjectAttendanceResponse(
        id=subject.id,
        code=subject.code,
        subject=subject.name,
        total_hours=subject.total_hours,
        attended_hours=subject.attended_hours,
        absent_hours=subject.absent_hours,
        source_percentage=float(subject.source_percentage),
        guidance=_guidance(guidance),
    )


@router.patch("/api/v1/settings", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    context: AuthContext = Depends(require_csrf),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> SettingsResponse:
    context.user.attendance_target = payload.attendance_target
    session.commit()
    return SettingsResponse(attendance_target=float(context.user.attendance_target))


@router.get("/api/v1/attendance", response_model=AttendanceResponse)
def get_attendance(
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> AttendanceResponse:
    subjects = session.scalars(
        select(Subject).where(Subject.user_id == context.user.id).order_by(Subject.code)
    ).all()
    total_hours = sum(subject.total_hours for subject in subjects)
    attended_hours = sum(subject.attended_hours for subject in subjects)
    overall = calculate_attendance_guidance(
        attended_hours,
        total_hours,
        context.user.attendance_target,
    )
    return AttendanceResponse(
        attendance_target=float(context.user.attendance_target),
        subjects=[
            _subject_response(subject, context.user.attendance_target) for subject in subjects
        ],
        overall=_guidance(overall),
        last_successful_sync=context.user.last_successful_sync_at,
    )


@router.get("/api/v1/subjects/{subject_id}/history", response_model=HistoryResponse)
def subject_history(
    subject_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    context: AuthContext = Depends(get_current_auth),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> HistoryResponse:
    subject = session.scalar(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == context.user.id)
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")

    query = select(AttendanceSnapshot).where(AttendanceSnapshot.subject_id == subject.id)
    if cursor is not None:
        query = query.where(AttendanceSnapshot.id < _decode_cursor(cursor))
    snapshots = session.scalars(query.order_by(AttendanceSnapshot.id.desc()).limit(limit + 1)).all()
    items = snapshots[:limit]
    next_cursor = _cursor(items[-1].id) if len(snapshots) > limit else None
    return HistoryResponse(
        items=[
            HistoryItem(
                id=snapshot.id,
                recorded_at=snapshot.recorded_at,
                total_hours=snapshot.total_hours,
                attended_hours=snapshot.attended_hours,
                absent_hours=snapshot.absent_hours,
                source_percentage=float(snapshot.source_percentage),
                guidance=_guidance(
                    calculate_attendance_guidance(
                        snapshot.attended_hours,
                        snapshot.total_hours,
                        context.user.attendance_target,
                    )
                ),
            )
            for snapshot in items
        ],
        next_cursor=next_cursor,
    )


@router.post("/api/v1/connector/attendance", response_model=UploadResponse)
def upload_attendance(
    payload: AttendanceUpload,
    connector: ConnectorContext = Depends(get_connector_context),  # noqa: B008
    session: DbSession = Depends(get_request_db),  # noqa: B008
) -> UploadResponse:
    try:
        result = process_upload(session, connector.device.id, payload)
    except UploadAuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid connector token",
        ) from error
    return UploadResponse(
        snapshots_created=result.snapshots_created,
        subjects_received=result.subjects_received,
        synced_at=result.synced_at,
    )
