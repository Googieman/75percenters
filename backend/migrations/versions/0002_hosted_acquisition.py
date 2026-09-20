"""Add the provider-independent hosted acquisition foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_hosted_acquisition"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UTC_NOW = sa.text("timezone('utc', now())")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_last_successful_sync_at", "users", ["last_successful_sync_at"])
    op.execute(
        sa.text(
            """
            UPDATE users
            SET last_successful_sync_at = latest.last_seen_at
            FROM (
                SELECT user_id, max(last_seen_at) AS last_seen_at
                FROM connector_devices
                WHERE last_seen_at IS NOT NULL
                GROUP BY user_id
            ) AS latest
            WHERE users.id = latest.user_id
            """
        )
    )

    op.create_table(
        "srm_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("verified_netid", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="disconnected"),
        sa.Column("encrypted_session_state", sa.LargeBinary()),
        sa.Column("session_key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("term_context", sa.String(length=128)),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True)),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_srm_connections_user_id"),
    )
    op.create_index("ix_srm_connections_user_id", "srm_connections", ["user_id"])

    op.create_table(
        "srm_auth_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer()),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("challenge_type", sa.String(length=32)),
        sa.Column("display_message", sa.String(length=255)),
        sa.Column("encrypted_state", sa.LargeBinary()),
        sa.Column("state_key_version", sa.Integer()),
        sa.Column("connection_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["srm_connections.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_srm_auth_attempts_user_id", "srm_auth_attempts", ["user_id"])
    op.create_index("ix_srm_auth_attempts_connection_id", "srm_auth_attempts", ["connection_id"])
    op.create_index("ix_srm_auth_attempts_expires_at", "srm_auth_attempts", ["expires_at"])

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer()),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("term_context", sa.String(length=128)),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_until", sa.DateTime(timezone=True)),
        sa.Column("fencing_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connection_generation", sa.Integer()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("result_code", sa.String(length=64)),
        sa.Column("last_error", sa.String(length=255)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["srm_connections.id"], ondelete="SET NULL"),
    )
    for name, columns in (
        ("ix_sync_jobs_user_id", ["user_id"]),
        ("ix_sync_jobs_connection_id", ["connection_id"]),
        ("ix_sync_jobs_status", ["status"]),
        ("ix_sync_jobs_scheduled_for", ["scheduled_for"]),
        ("ix_sync_jobs_claimed_until", ["claimed_until"]),
        ("ix_sync_jobs_retry_at", ["retry_at"]),
    ):
        op.create_index(name, "sync_jobs", columns)

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=255)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=UTC_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
    )
    op.create_index("ix_notification_outbox_user_id", "notification_outbox", ["user_id"])
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_index("ix_notification_outbox_available_at", "notification_outbox", ["available_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_available_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_status", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_user_id", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    for name in (
        "ix_sync_jobs_retry_at",
        "ix_sync_jobs_claimed_until",
        "ix_sync_jobs_scheduled_for",
        "ix_sync_jobs_status",
        "ix_sync_jobs_connection_id",
        "ix_sync_jobs_user_id",
    ):
        op.drop_index(name, table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_index("ix_srm_auth_attempts_expires_at", table_name="srm_auth_attempts")
    op.drop_index("ix_srm_auth_attempts_connection_id", table_name="srm_auth_attempts")
    op.drop_index("ix_srm_auth_attempts_user_id", table_name="srm_auth_attempts")
    op.drop_table("srm_auth_attempts")
    op.drop_index("ix_srm_connections_user_id", table_name="srm_connections")
    op.drop_table("srm_connections")
    op.drop_index("ix_users_last_successful_sync_at", table_name="users")
    op.drop_column("users", "last_successful_sync_at")
