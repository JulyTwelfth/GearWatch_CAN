from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Identity, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.fetch_status import FetchStatus
    from app.models.listing import Listing


class Retailer(TimestampMixin, Base):
    __tablename__ = "retailers"
    __table_args__ = (UniqueConstraint("slug", name="uq_retailers_slug"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="retailer", cascade="all, delete-orphan"
    )
    fetch_statuses: Mapped[list["FetchStatus"]] = relationship(
        back_populates="retailer", cascade="all, delete-orphan"
    )
