from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    FetchStatus,
    InventorySnapshot,
    Listing,
    ListingVariant,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.repositories import (
    deactivate_missing_listing_variants,
    ingest_retailer_listing,
    record_fetch_status,
)
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
    assert product.identity_key == "style:x000009859"


def test_same_style_matches_across_retailers_despite_name_differences(
    db_session: Session,
) -> None:
    first = ingest_retailer_listing(
        db_session,
        make_listing(
            retailer="Arc'teryx Outlet Canada",
            product_name="Beta AR Jacket Men's",
            model_name="Beta AR Jacket",
            model_number="X000009906",
            product_url="https://outlet.example.invalid/beta-ar",
        ),
    )
    second = ingest_retailer_listing(
        db_session,
        make_listing(
            retailer="Monod Sports",
            product_name="Arc'teryx Beta AR Jacket (Past Season) Men's",
            model_name="Beta AR Jacket",
            model_number="X000009906",
            product_url="https://monod.example.invalid/beta-ar",
        ),
    )

    assert first.product_id == second.product_id
    assert count_rows(db_session, Product) == 1
    assert count_rows(db_session, Listing) == 2


def test_different_style_numbers_are_never_merged_by_similar_model_name(
    db_session: Session,
) -> None:
    first = ingest_retailer_listing(
        db_session,
        make_listing(
            model_name="Beta Jacket",
            model_number="X000010511",
            product_url="https://example.com/products/beta-current",
        ),
    )
    second = ingest_retailer_listing(
        db_session,
        make_listing(
            model_name="Beta Jacket",
            model_number="X000010878",
            product_url="https://example.com/products/beta-revised",
        ),
    )

    assert first.product_id != second.product_id
    assert count_rows(db_session, Product) == 2


def test_reviewed_model_alias_can_match_when_style_number_is_missing(
    db_session: Session,
) -> None:
    first = ingest_retailer_listing(
        db_session,
        make_listing(
            product_name="Atom LT Hoody Men's",
            model_name="Atom LT Hoody",
            model_number=None,
            gender="Men",
            product_url="https://example.com/products/atom-lt",
        ),
    )
    second = ingest_retailer_listing(
        db_session,
        make_listing(
            product_name="Atom Hoody Men's",
            model_name="Atom Hoody",
            model_number=None,
            gender="Men",
            product_url="https://other.example.com/products/atom",
        ),
    )

    assert first.product_id == second.product_id
    assert count_rows(db_session, Product) == 1


def test_model_fallback_does_not_merge_known_different_categories(
    db_session: Session,
) -> None:
    first = ingest_retailer_listing(
        db_session,
        make_listing(
            product_name="Gamma Jacket Men's",
            model_name="Gamma Jacket",
            model_number=None,
            category="Shell",
            product_url="https://example.com/products/gamma-shell",
        ),
    )
    second = ingest_retailer_listing(
        db_session,
        make_listing(
            product_name="Gamma Jacket Men's",
            model_name="Gamma Jacket",
            model_number=None,
            category="Insulation",
            product_url="https://other.example.com/products/gamma-insulation",
        ),
    )

    assert first.product_id != second.product_id
    assert count_rows(db_session, Product) == 2


def test_variant_sku_and_failed_fetch_status_are_persisted(db_session: Session) -> None:
    checked_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    data = make_listing(variant_sku="RETAILER-SKU-M", checked_at=checked_at)
    result = ingest_retailer_listing(db_session, data)

    created = record_fetch_status(
        db_session,
        retailer_name=data.retailer,
        source_url=str(data.product_url),
        status="blocked",
        error_type="HttpFetchError",
        checked_at=checked_at + timedelta(hours=1),
    )

    link = db_session.scalar(select(ListingVariant))
    listing = db_session.get(Listing, result.listing_id)
    fetch = db_session.scalar(select(FetchStatus))
    assert created is True
    assert link is not None
    assert link.retailer_sku == "RETAILER-SKU-M"
    assert listing is not None
    assert listing.source_status == "blocked"
    assert listing.last_checked_at == checked_at
    assert listing.status_checked_at == checked_at + timedelta(hours=1)
    assert fetch is not None
    assert fetch.error_type == "HttpFetchError"


def test_successful_check_deactivates_variants_missing_from_current_page(
    db_session: Session,
) -> None:
    checked_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    old_variant = make_listing(
        color="Black Sapphire",
        size="L",
        variant_sku="OLD-L",
        checked_at=checked_at,
    )
    current_variant = make_listing(
        color="Lodestar",
        size="XL",
        variant_sku="CURRENT-XL",
        checked_at=checked_at,
    )
    ingest_retailer_listing(db_session, old_variant)
    ingest_retailer_listing(db_session, current_variant)

    next_check = checked_at + timedelta(hours=1)
    ingest_retailer_listing(
        db_session,
        make_listing(
            color="Lodestar",
            size="XL",
            variant_sku="CURRENT-XL",
            checked_at=next_check,
        ),
    )
    deactivated = deactivate_missing_listing_variants(
        db_session,
        retailer_name=current_variant.retailer,
        source_url=str(current_variant.product_url),
        checked_at=next_check,
    )

    links = db_session.scalars(
        select(ListingVariant).order_by(ListingVariant.retailer_sku)
    ).all()
    assert deactivated == 1
    assert [(link.retailer_sku, link.is_active) for link in links] == [
        ("CURRENT-XL", True),
        ("OLD-L", False),
    ]
