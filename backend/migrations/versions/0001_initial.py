"""Create the authenticated attendance schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "attendance_target", sa.Numeric(5, 2), server_default=sa.text("75.00"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("total_hours", sa.Integer(), nullable=False),
        sa.Column("attended_hours", sa.Integer(), nullable=False),
        sa.Column("absent_hours", sa.Integer(), nullable=False),
        sa.Column("source_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "code", name="uq_subject_user_code"),
    )
    op.create_index("ix_subjects_user_id", "subjects", ["user_id"])
    op.create_table(
        "attendance_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("total_hours", sa.Integer(), nullable=False),
        sa.Column("attended_hours", sa.Integer(), nullable=False),
        sa.Column("absent_hours", sa.Integer(), nullable=False),
        sa.Column("source_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_attendance_snapshots_subject_id", "attendance_snapshots", ["subject_id"])
    op.create_index("ix_attendance_snapshots_recorded_at", "attendance_snapshots", ["recorded_at"])
    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("code_hash", name="uq_pairing_codes_code_hash"),
    )
    op.create_index("ix_pairing_codes_user_id", "pairing_codes", ["user_id"])
    op.create_index("ix_pairing_codes_code_hash", "pairing_codes", ["code_hash"])
    op.create_index("ix_pairing_codes_expires_at", "pairing_codes", ["expires_at"])
    op.create_table(
        "connector_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_connector_devices_token_hash"),
    )
    op.create_index("ix_connector_devices_user_id", "connector_devices", ["user_id"])
    op.create_index("ix_connector_devices_token_hash", "connector_devices", ["token_hash"])
    op.create_index("ix_connector_devices_last_seen_at", "connector_devices", ["last_seen_at"])
    op.create_index("ix_connector_devices_revoked_at", "connector_devices", ["revoked_at"])
    op.create_table(
        "rate_limit_buckets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer()),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("action", "key", name="uq_rate_limit_action_key"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_connector_devices_revoked_at", table_name="connector_devices")
    op.drop_index("ix_connector_devices_last_seen_at", table_name="connector_devices")
    op.drop_index("ix_connector_devices_token_hash", table_name="connector_devices")
    op.drop_index("ix_connector_devices_user_id", table_name="connector_devices")
    op.drop_table("connector_devices")
    op.drop_index("ix_pairing_codes_expires_at", table_name="pairing_codes")
    op.drop_index("ix_pairing_codes_code_hash", table_name="pairing_codes")
    op.drop_index("ix_pairing_codes_user_id", table_name="pairing_codes")
    op.drop_table("pairing_codes")
    op.drop_index("ix_attendance_snapshots_recorded_at", table_name="attendance_snapshots")
    op.drop_index("ix_attendance_snapshots_subject_id", table_name="attendance_snapshots")
    op.drop_table("attendance_snapshots")
    op.drop_index("ix_subjects_user_id", table_name="subjects")
    op.drop_table("subjects")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
