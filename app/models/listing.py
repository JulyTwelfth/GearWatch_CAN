from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory_snapshot import InventorySnapshot
    from app.models.price_snapshot import PriceSnapshot
    from app.models.product import Product
    from app.models.retailer import Retailer


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("retailer_id", "url_hash", name="uq_listings_retailer_url_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retailer_id: Mapped[int] = mapped_column(
        ForeignKey("retailers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(150))
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success"
    )
    status_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_error_type: Mapped[str | None] = mapped_column(String(100))

    product: Mapped["Product"] = relationship(back_populates="listings")
    retailer: Mapped["Retailer"] = relationship(back_populates="listings")
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    inventory_snapshots: Mapped[list["InventorySnapshot"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
