from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.product_variant import ProductVariant


class PriceSnapshot(CreatedAtMixin, Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "variant_id", "checked_at", name="uq_price_snapshots_point"
        ),
        CheckConstraint("current_price >= 0", name="ck_price_snapshots_current_nonnegative"),
        CheckConstraint(
            "original_price IS NULL OR original_price >= current_price",
            name="ck_price_snapshots_original_valid",
        ),
        CheckConstraint(
            "discount_percentage >= 0 AND discount_percentage <= 100",
            name="ck_price_snapshots_discount_range",
        ),
        Index("ix_price_snapshots_history", "listing_id", "variant_id", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    current_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    discount_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    listing: Mapped["Listing"] = relationship(back_populates="price_snapshots")
    variant: Mapped["ProductVariant"] = relationship(back_populates="price_snapshots")

