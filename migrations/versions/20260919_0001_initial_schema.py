"""Create the initial GearWatch persistence schema.

Revision ID: 20260919_0001
Revises:
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("model_number", sa.String(length=100), nullable=True),
        sa.Column("normalized_model_number", sa.String(length=100), nullable=True),
        sa.Column("identity_key", sa.String(length=300), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand", "identity_key", name="uq_products_brand_identity"),
    )
    op.create_index("ix_products_normalized_name", "products", ["normalized_name"])
    op.create_index(
        "ix_products_normalized_model_number", "products", ["normalized_model_number"]
    )

    op.create_table(
        "retailers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_retailers_slug"),
    )

    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("retailer_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(length=150), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retailer_id", "url_hash", name="uq_listings_retailer_url_hash"),
    )
    op.create_index("ix_listings_product_id", "listings", ["product_id"])
    op.create_index("ix_listings_retailer_id", "listings", ["retailer_id"])

    op.create_table(
        "product_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("color", sa.String(length=150), nullable=False),
        sa.Column("normalized_color", sa.String(length=150), nullable=False),
        sa.Column("size", sa.String(length=50), nullable=False),
        sa.Column("normalized_size", sa.String(length=50), nullable=False),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "normalized_color",
            "normalized_size",
            name="uq_product_variants_identity",
        ),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])
    op.create_index(
        "ix_product_variants_normalized_color", "product_variants", ["normalized_color"]
    )
    op.create_index(
        "ix_product_variants_normalized_size", "product_variants", ["normalized_size"]
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("original_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("discount_percentage", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "current_price >= 0", name="ck_price_snapshots_current_nonnegative"
        ),
        sa.CheckConstraint(
            "discount_percentage >= 0 AND discount_percentage <= 100",
            name="ck_price_snapshots_discount_range",
        ),
        sa.CheckConstraint(
            "original_price IS NULL OR original_price >= current_price",
            name="ck_price_snapshots_original_valid",
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["product_variants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "listing_id", "variant_id", "checked_at", name="uq_price_snapshots_point"
        ),
    )
    op.create_index(
        "ix_price_snapshots_history",
        "price_snapshots",
        ["listing_id", "variant_id", "checked_at"],
    )

    inventory_status = sa.Enum(
        "Available",
        "Out of Stock",
        "Unknown",
        name="inventory_stock_status",
        native_enum=False,
        create_constraint=True,
        length=20,
    )
    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("stock_status", inventory_status, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
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
            "listing_id", "variant_id", "checked_at", name="uq_inventory_snapshots_point"
        ),
    )
    op.create_index(
        "ix_inventory_snapshots_history",
        "inventory_snapshots",
        ["listing_id", "variant_id", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_snapshots_history", table_name="inventory_snapshots")
    op.drop_table("inventory_snapshots")
    op.drop_index("ix_price_snapshots_history", table_name="price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_index("ix_product_variants_normalized_size", table_name="product_variants")
    op.drop_index("ix_product_variants_normalized_color", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index("ix_listings_retailer_id", table_name="listings")
    op.drop_index("ix_listings_product_id", table_name="listings")
    op.drop_table("listings")
    op.drop_table("retailers")
    op.drop_index("ix_products_normalized_model_number", table_name="products")
    op.drop_index("ix_products_normalized_name", table_name="products")
    op.drop_table("products")
