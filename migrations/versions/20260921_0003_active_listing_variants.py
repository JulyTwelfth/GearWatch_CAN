"""Track which retailer variants are present in the latest successful check.

Revision ID: 20260921_0003
Revises: 20260920_0002
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0003"
down_revision: str | Sequence[str] | None = "20260920_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_variants",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "listing_variants",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE listing_variants AS lv SET last_seen_at = l.last_checked_at "
        "FROM listings AS l WHERE l.id = lv.listing_id"
    )
    op.alter_column("listing_variants", "last_seen_at", nullable=False)
    op.create_index(
        "ix_listing_variants_is_active", "listing_variants", ["is_active"]
    )
    op.create_index(
        "ix_listing_variants_last_seen_at", "listing_variants", ["last_seen_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_listing_variants_last_seen_at", table_name="listing_variants")
    op.drop_index("ix_listing_variants_is_active", table_name="listing_variants")
    op.drop_column("listing_variants", "last_seen_at")
    op.drop_column("listing_variants", "is_active")
