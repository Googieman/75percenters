"""Keep requested and provider-verified identities separate."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_pending_identity"
down_revision: str | None = "0002_hosted_acquisition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "srm_connections", "verified_netid", existing_type=sa.String(128), nullable=True
    )
    op.add_column("srm_connections", sa.Column("pending_netid", sa.String(length=128)))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE srm_connections
            SET verified_netid = pending_netid
            WHERE verified_netid IS NULL AND pending_netid IS NOT NULL
            """
        )
    )
    op.drop_column("srm_connections", "pending_netid")
    op.execute(
        sa.text(
            "UPDATE srm_connections SET verified_netid = COALESCE(verified_netid, 'unknown')"
        )
    )
    op.alter_column(
        "srm_connections", "verified_netid", existing_type=sa.String(128), nullable=False
    )
