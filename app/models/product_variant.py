from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory_snapshot import InventorySnapshot
    from app.models.listing_variant import ListingVariant
    from app.models.price_snapshot import PriceSnapshot
    from app.models.product import Product


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "normalized_color",
            "normalized_size",
            name="uq_product_variants_identity",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    color: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_color: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    size: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_size: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    product: Mapped["Product"] = relationship(back_populates="variants")
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )
    inventory_snapshots: Mapped[list["InventorySnapshot"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )
    listing_variants: Mapped[list["ListingVariant"]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )
