"""Add durable scheduling metadata and per-subscription notification delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_scheduling_notifications"
down_revision: str | None = "0003_pending_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "srm_connections",
        sa.Column("next_scheduled_refresh", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_srm_connections_next_scheduled_refresh",
        "srm_connections",
        ["next_scheduled_refresh"],
    )
    op.create_index(
        "uq_sync_jobs_active_connection",
        "sync_jobs",
        ["connection_id"],
        unique=True,
        postgresql_where=sa.text(
            "connection_id IS NOT NULL AND status IN ('queued', 'claimed')"
        ),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=255)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notification_outbox.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["push_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "notification_id", "subscription_id", name="uq_notification_delivery_target"
        ),
    )
    for name, columns in (
        ("ix_notification_deliveries_notification_id", ["notification_id"]),
        ("ix_notification_deliveries_subscription_id", ["subscription_id"]),
        ("ix_notification_deliveries_status", ["status"]),
        ("ix_notification_deliveries_available_at", ["available_at"]),
    ):
        op.create_index(name, "notification_deliveries", columns)


def downgrade() -> None:
    for name in (
        "ix_notification_deliveries_available_at",
        "ix_notification_deliveries_status",
        "ix_notification_deliveries_subscription_id",
        "ix_notification_deliveries_notification_id",
    ):
        op.drop_index(name, table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("uq_sync_jobs_active_connection", table_name="sync_jobs")
    op.drop_index(
        "ix_srm_connections_next_scheduled_refresh", table_name="srm_connections"
    )
    op.drop_column("srm_connections", "next_scheduled_refresh")
