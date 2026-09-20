from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Listing,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.repositories import ingest_retailer_listing
from app.schemas.retailer import RetailerListing

pytestmark = pytest.mark.integration


def make_listing(**overrides: object) -> RetailerListing:
    values: dict[str, object] = {
        "brand": "Arc'teryx",
        "product_name": "Arc'teryx Beta Jacket - Men's",
        "model_number": "X000009859",
        "retailer": "MEC",
        "current_price": "375.00",
        "original_price": "500.00",
        "currency": "CAD",
        "color": "Black Sapphire",
        "size": "M",
        "stock_status": "Available",
        "product_url": "https://www.example.com/products/beta-jacket",
        "checked_at": datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return RetailerListing.model_validate(values)


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_ingest_writes_complete_listing_graph(db_session: Session) -> None:
    result = ingest_retailer_listing(db_session, make_listing())

    assert result.price_snapshot_created is True
    assert result.inventory_snapshot_created is True
    assert count_rows(db_session, Product) == 1
    assert count_rows(db_session, Retailer) == 1
    assert count_rows(db_session, Listing) == 1
    assert count_rows(db_session, ProductVariant) == 1
    assert count_rows(db_session, PriceSnapshot) == 1
    assert count_rows(db_session, InventorySnapshot) == 1


def test_duplicate_timepoint_does_not_create_duplicate_data(db_session: Session) -> None:
    first = ingest_retailer_listing(db_session, make_listing())
    duplicate = ingest_retailer_listing(db_session, make_listing())

    assert duplicate.product_id == first.product_id
    assert duplicate.listing_id == first.listing_id
    assert duplicate.variant_id == first.variant_id
    assert duplicate.price_snapshot_created is False
    assert duplicate.inventory_snapshot_created is False
    assert count_rows(db_session, Product) == 1
    assert count_rows(db_session, Listing) == 1
    assert count_rows(db_session, ProductVariant) == 1
    assert count_rows(db_session, PriceSnapshot) == 1
    assert count_rows(db_session, InventorySnapshot) == 1


def test_changed_values_append_only_relevant_snapshots(db_session: Session) -> None:
    checked_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    ingest_retailer_listing(db_session, make_listing(checked_at=checked_at))

    price_change = ingest_retailer_listing(
        db_session,
        make_listing(
            current_price="350.00",
            checked_at=checked_at + timedelta(hours=1),
        ),
    )
    inventory_change = ingest_retailer_listing(
        db_session,
        make_listing(
            current_price="350.00",
            stock_status="Out of Stock",
            checked_at=checked_at + timedelta(hours=2),
        ),
    )

    assert price_change.price_snapshot_created is True
    assert price_change.inventory_snapshot_created is False
    assert inventory_change.price_snapshot_created is False
    assert inventory_change.inventory_snapshot_created is True
    assert count_rows(db_session, PriceSnapshot) == 2
    assert count_rows(db_session, InventorySnapshot) == 2

    latest_price = db_session.scalar(
        select(PriceSnapshot).order_by(PriceSnapshot.checked_at.desc()).limit(1)
    )
    listing = db_session.scalar(select(Listing))
    assert latest_price is not None
    assert latest_price.current_price == Decimal("350.00")
    assert listing is not None
    assert listing.last_checked_at == checked_at + timedelta(hours=2)


def test_later_model_number_promotes_existing_product(db_session: Session) -> None:
    checked_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    first = ingest_retailer_listing(
        db_session,
        make_listing(model_number=None, checked_at=checked_at),
    )
    second = ingest_retailer_listing(
        db_session,
        make_listing(checked_at=checked_at + timedelta(hours=1)),
    )

    product = db_session.scalar(select(Product))
    assert first.product_id == second.product_id
    assert count_rows(db_session, Product) == 1
    assert product is not None
    assert product.model_number == "X000009859"
    assert product.identity_key == "model:x000009859"
