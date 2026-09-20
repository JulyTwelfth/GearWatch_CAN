from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin
from app.services.normalization import StockStatus

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.product_variant import ProductVariant


class InventorySnapshot(CreatedAtMixin, Base):
    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "variant_id", "checked_at", name="uq_inventory_snapshots_point"
        ),
        Index("ix_inventory_snapshots_history", "listing_id", "variant_id", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    stock_status: Mapped[StockStatus] = mapped_column(
        Enum(
            StockStatus,
            values_callable=lambda enum: [item.value for item in enum],
            name="inventory_stock_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=20,
        ),
        nullable=False,
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    listing: Mapped["Listing"] = relationship(back_populates="inventory_snapshots")
    variant: Mapped["ProductVariant"] = relationship(back_populates="inventory_snapshots")

