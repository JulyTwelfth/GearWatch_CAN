from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.product_variant import ProductVariant


class ListingVariant(TimestampMixin, Base):
    """Retailer-specific SKU mapped to one canonical colour/size variant."""

    __tablename__ = "listing_variants"
    __table_args__ = (
        UniqueConstraint("listing_id", "variant_id", name="uq_listing_variants_identity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retailer_sku: Mapped[str | None] = mapped_column(String(150), index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    listing: Mapped["Listing"] = relationship()
    variant: Mapped["ProductVariant"] = relationship(back_populates="listing_variants")
