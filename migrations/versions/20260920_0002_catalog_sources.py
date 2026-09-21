"""Expand canonical catalogue metadata and source-status tracking.

Revision ID: 20260920_0002
Revises: 20260919_0001
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0002"
down_revision: str | Sequence[str] | None = "20260919_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("model_name", sa.String(150), nullable=True))
    op.add_column(
        "products", sa.Column("normalized_model_name", sa.String(150), nullable=True)
    )
    op.add_column("products", sa.Column("style_number", sa.String(100), nullable=True))
    op.add_column(
        "products", sa.Column("normalized_style_number", sa.String(100), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("gender", sa.String(20), server_default="Unknown", nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("category", sa.String(100), server_default="Other", nullable=False),
    )
    op.add_column("products", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.Text(), nullable=True))
    op.execute(
        "UPDATE products SET style_number = model_number, "
        "normalized_style_number = normalized_model_number"
    )
    op.create_index("ix_products_normalized_model_name", "products", ["normalized_model_name"])
    op.create_index(
        "ix_products_normalized_style_number", "products", ["normalized_style_number"]
    )
    op.create_index("ix_products_gender", "products", ["gender"])
    op.create_index("ix_products_category", "products", ["category"])

    op.add_column(
        "listings",
        sa.Column("source_status", sa.String(20), server_default="success", nullable=False),
    )
    op.add_column(
        "listings", sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("listings", sa.Column("last_error_type", sa.String(100), nullable=True))
    op.execute("UPDATE listings SET status_checked_at = last_checked_at")
    op.alter_column("listings", "status_checked_at", nullable=False)

    op.create_table(
        "listing_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("retailer_sku", sa.String(150), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "listing_id", "variant_id", name="uq_listing_variants_identity"
        ),
    )
    op.create_index("ix_listing_variants_listing_id", "listing_variants", ["listing_id"])
    op.create_index("ix_listing_variants_variant_id", "listing_variants", ["variant_id"])
    op.create_index("ix_listing_variants_retailer_sku", "listing_variants", ["retailer_sku"])

    op.create_table(
        "fetch_statuses",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("retailer_id", sa.BigInteger(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "retailer_id", "url_hash", "checked_at", name="uq_fetch_statuses_point"
        ),
    )
    op.create_index(
        "ix_fetch_statuses_latest",
        "fetch_statuses",
        ["retailer_id", "url_hash", "checked_at"],
    )
    op.create_index(
        "ix_fetch_statuses_status_checked", "fetch_statuses", ["status", "checked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_fetch_statuses_status_checked", table_name="fetch_statuses")
    op.drop_index("ix_fetch_statuses_latest", table_name="fetch_statuses")
    op.drop_table("fetch_statuses")
    op.drop_index("ix_listing_variants_retailer_sku", table_name="listing_variants")
    op.drop_index("ix_listing_variants_variant_id", table_name="listing_variants")
    op.drop_index("ix_listing_variants_listing_id", table_name="listing_variants")
    op.drop_table("listing_variants")
    op.drop_column("listings", "last_error_type")
    op.drop_column("listings", "status_checked_at")
    op.drop_column("listings", "source_status")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_gender", table_name="products")
    op.drop_index("ix_products_normalized_style_number", table_name="products")
    op.drop_index("ix_products_normalized_model_name", table_name="products")
    op.drop_column("products", "image_url")
    op.drop_column("products", "canonical_url")
    op.drop_column("products", "category")
    op.drop_column("products", "gender")
    op.drop_column("products", "normalized_style_number")
    op.drop_column("products", "style_number")
    op.drop_column("products", "normalized_model_name")
    op.drop_column("products", "model_name")
