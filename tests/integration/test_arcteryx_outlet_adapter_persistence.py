from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.models import InventorySnapshot, Listing, PriceSnapshot, Product, ProductVariant, Retailer
from app.repositories import ingest_retailer_listing

pytestmark = pytest.mark.integration

FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "retailers"
    / "arcteryx_outlet"
    / "product_sale.html"
)
PRODUCT_URL = "https://outlet.arcteryx.com/ca/en/shop/mens/fixture-alpine-shell-9998"


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_outlet_adapter_rows_are_deduplicated_in_postgresql(db_session: Session) -> None:
    listings = ArcTeryxOutletAdapter().parse_product_page(
        FIXTURE_PATH.read_text(encoding="utf-8"),
        product_url=PRODUCT_URL,
        checked_at=datetime(2026, 9, 19, 18, 0, tzinfo=UTC),
    )

    for listing in listings:
        ingest_retailer_listing(db_session, listing)
    for listing in listings:
        ingest_retailer_listing(db_session, listing)

    assert count_rows(db_session, Product) == 1
    assert count_rows(db_session, Retailer) == 1
    assert count_rows(db_session, Listing) == 1
    assert count_rows(db_session, ProductVariant) == 3
    assert count_rows(db_session, PriceSnapshot) == 3
    assert count_rows(db_session, InventorySnapshot) == 3
