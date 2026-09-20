"""Strict HTTP payload and response schemas for attendance state."""

from datetime import datetime
from decimal import Decimal
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class SubjectUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=255)
    total_hours: StrictInt = Field(ge=0)
    attended_hours: StrictInt = Field(ge=0)
    absent_hours: StrictInt = Field(ge=0)
    source_percentage: Decimal

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("subject code must not be blank")
        return value

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("subject name must not be blank")
        return value

    @field_validator("source_percentage")
    @classmethod
    def validate_percentage(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
            raise ValueError("source percentage must be finite and between 0 and 100")
        return value

    @model_validator(mode="after")
    def validate_totals(self) -> "SubjectUpload":
        if self.attended_hours + self.absent_hours != self.total_hours:
            raise ValueError("attended plus absent hours must equal total hours")
        return self


class AttendanceUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[SubjectUpload] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def reject_duplicate_codes(self) -> "AttendanceUpload":
        codes = [subject.code for subject in self.subjects]
        if len(codes) != len(set(codes)):
            raise ValueError("upload contains duplicate subject codes")
        return self


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attendance_target: Decimal

    @field_validator("attendance_target")
    @classmethod
    def validate_target(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") < value <= Decimal("100"):
            raise ValueError("attendance target must be greater than 0 and at most 100")
        return value


class GuidanceResponse(BaseModel):
    current_percentage: float | None
    additional_attended_hours: int | None
    additional_absences_allowed: int | None
    target_reachable: bool


class SubjectAttendanceResponse(BaseModel):
    id: int
    code: str
    subject: str
    total_hours: int
    attended_hours: int
    absent_hours: int
    source_percentage: float
    guidance: GuidanceResponse


class AttendanceResponse(BaseModel):
    attendance_target: float
    subjects: list[SubjectAttendanceResponse]
    overall: GuidanceResponse
    last_successful_sync: datetime | None


class SettingsResponse(BaseModel):
    attendance_target: float


class UploadResponse(BaseModel):
    snapshots_created: int
    subjects_received: int
    synced_at: datetime


class HistoryItem(BaseModel):
    id: int
    recorded_at: datetime
    total_hours: int
    attended_hours: int
    absent_hours: int
    source_percentage: float
    guidance: GuidanceResponse


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None


class SrmConnectionResponse(BaseModel):
    status: str
    provider: str | None
    provider_available: bool
    netid_hint: str | None
    last_authenticated_at: datetime | None
    last_refreshed_at: datetime | None
    last_successful_sync: datetime | None
    active_job_id: int | None
    next_scheduled_refresh: datetime | None
    last_error_code: str | None
    notifications_available: bool


class AuthAttemptStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    netid: str = Field(min_length=1, max_length=128)

    @field_validator("netid")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value must not be blank")
        return value


class AuthAttemptCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str | None = Field(default=None, min_length=1, max_length=1024)
    response: str | None = Field(default=None, min_length=1, max_length=1024)


class AuthAttemptResponse(BaseModel):
    attempt_id: int
    status: str
    challenge_type: str | None
    message: str | None
    expires_at: datetime


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SyncJobResponse(BaseModel):
    job_id: int
    status: str
    scheduled_for: datetime
    attempt_count: int
    result_code: str | None
    retry_at: datetime | None
    completed_at: datetime | None


class PushSubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: AnyHttpUrl
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def supported_public_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        parsed = urlsplit(str(value))
        hostname = (parsed.hostname or "").lower().rstrip(".")
        allowed_hosts = (
            "fcm.googleapis.com",
            "updates.push.services.mozilla.com",
            "push.services.mozilla.com",
            "notify.windows.com",
            "web.push.apple.com",
        )
        try:
            parsed_ip = ip_address(hostname)
        except ValueError:
            parsed_ip = None
        allowed = any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts)
        if parsed.scheme != "https" or not hostname or parsed_ip is not None or not allowed:
            raise ValueError("push endpoint must be a supported public HTTPS service")
        return value


class PushSubscriptionResponse(BaseModel):
    subscription_id: int
