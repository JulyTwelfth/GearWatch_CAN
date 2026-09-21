from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.retailer import Retailer


class FetchStatus(CreatedAtMixin, Base):
    """Append-only outcome for one retailer resource check."""

    __tablename__ = "fetch_statuses"
    __table_args__ = (
        UniqueConstraint(
            "retailer_id", "url_hash", "checked_at", name="uq_fetch_statuses_point"
        ),
        Index("ix_fetch_statuses_latest", "retailer_id", "url_hash", "checked_at"),
        Index("ix_fetch_statuses_status_checked", "status", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    retailer_id: Mapped[int] = mapped_column(
        ForeignKey("retailers.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    retailer: Mapped["Retailer"] = relationship(back_populates="fetch_statuses")
