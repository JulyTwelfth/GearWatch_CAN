from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Identity, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.listing import Listing
    from app.models.product_variant import ProductVariant


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("brand", "identity_key", name="uq_products_brand_identity"),
        Index("ix_products_normalized_name", "normalized_name"),
        Index("ix_products_normalized_model_number", "normalized_model_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_number: Mapped[str | None] = mapped_column(String(100))
    normalized_model_number: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(150))
    normalized_model_name: Mapped[str | None] = mapped_column(String(150), index=True)
    style_number: Mapped[str | None] = mapped_column(String(100))
    normalized_style_number: Mapped[str | None] = mapped_column(String(100), index=True)
    gender: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Unknown", index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Other", index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    identity_key: Mapped[str] = mapped_column(String(300), nullable=False)

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
