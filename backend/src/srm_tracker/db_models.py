"""Persistent ownership and attendance records."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from srm_tracker.db import Base

UTC_NOW = text("timezone('utc', now())")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    attendance_target: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("75.00"), default=Decimal("75.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subjects: Mapped[list["Subject"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pairing_codes: Mapped[list["PairingCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    devices: Mapped[list["ConnectorDevice"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    rate_limits: Mapped[list["RateLimitBucket"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    srm_connection: Mapped["SrmConnection | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    auth_attempts: Mapped[list["AuthAttempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sync_jobs: Mapped[list["SyncJob"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notification_outbox: Mapped[list["NotificationOutbox"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_subject_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    attended_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    absent_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    source_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="subjects")
    snapshots: Mapped[list["AttendanceSnapshot"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan", order_by="AttendanceSnapshot.id"
    )


class AttendanceSnapshot(Base):
    __tablename__ = "attendance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    total_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    attended_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    absent_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    source_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, index=True
    )

    subject: Mapped[Subject] = relationship(back_populates="snapshots")


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="pairing_codes")


class ConnectorDevice(Base):
    __tablename__ = "connector_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(back_populates="devices")


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (UniqueConstraint("action", "key", name="uq_rate_limit_action_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(255))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="rate_limits")


class SrmConnection(Base):
    """The owner-scoped, server-side SRM session boundary."""

    __tablename__ = "srm_connections"
    __table_args__ = (UniqueConstraint("user_id", name="uq_srm_connections_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verified_netid: Mapped[str | None] = mapped_column(String(128))
    pending_netid: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    encrypted_session_state: Mapped[bytes | None] = mapped_column(LargeBinary)
    session_key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    term_context: Mapped[str | None] = mapped_column(String(128))
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_scheduled_refresh: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="srm_connection")
    auth_attempts: Mapped[list["AuthAttempt"]] = relationship(back_populates="connection")
    sync_jobs: Mapped[list["SyncJob"]] = relationship(back_populates="connection")


class AuthAttempt(Base):
    """Short-lived challenge state; transient credentials are never persisted."""

    __tablename__ = "srm_auth_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("srm_connections.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    challenge_type: Mapped[str | None] = mapped_column(String(32))
    display_message: Mapped[str | None] = mapped_column(String(255))
    encrypted_state: Mapped[bytes | None] = mapped_column(LargeBinary)
    state_key_version: Mapped[int | None] = mapped_column(Integer)
    connection_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="auth_attempts")
    connection: Mapped[SrmConnection | None] = relationship(back_populates="auth_attempts")


class SyncJob(Base):
    """A durable, fenced acquisition job claimed by a worker."""

    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("srm_connections.id", ondelete="SET NULL"), index=True
    )
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    term_context: Mapped[str | None] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    claimed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fencing_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connection_generation: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    result_code: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW, onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="sync_jobs")
    connection: Mapped[SrmConnection | None] = relationship(back_populates="sync_jobs")


class PushSubscription(Base):
    """Owner-scoped Web Push endpoint material."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(2048))
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )

    user: Mapped[User] = relationship(back_populates="push_subscriptions")


class NotificationOutbox(Base):
    """Durable, deduplicated notification intent without sensitive payloads."""

    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(255))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=UTC_NOW
    )

    user: Mapped[User] = relationship(back_populates="notification_outbox")
    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="notice", cascade="all, delete-orphan"
    )


class NotificationDelivery(Base):
    """Per-subscription delivery state for at-least-once Web Push."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "subscription_id", name="uq_notification_delivery_target"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notification_outbox.id", ondelete="CASCADE"), index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("push_subscriptions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_error: Mapped[str | None] = mapped_column(String(255))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notice: Mapped[NotificationOutbox] = relationship(back_populates="deliveries")
    subscription: Mapped[PushSubscription] = relationship()
