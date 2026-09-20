from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.repositories import ingest_retailer_listing
from app.schemas.retailer import RetailerListing
from app.schemas.search import ProductSearchParams
from app.services.normalization import StockStatus
from app.services.product_search import ProductSearchService

pytestmark = pytest.mark.integration

BASE_TIME = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)


def listing(
    *,
    retailer: str,
    url_slug: str,
    color: str,
    size: str,
    current_price: str,
    original_price: str | None,
    stock_status: str,
    checked_at: datetime = BASE_TIME,
) -> RetailerListing:
    return RetailerListing.model_validate(
        {
            "brand": "Arc'teryx",
            "product_name": "Fixture Alpine Search Shell",
            "model_number": "X000066666",
            "retailer": retailer,
            "current_price": current_price,
            "original_price": original_price,
            "currency": "CAD",
            "color": color,
            "size": size,
            "stock_status": stock_status,
            "product_url": f"https://example.invalid/{url_slug}",
            "checked_at": checked_at,
        }
    )


def seed_search_data(session: Session) -> None:
    rows = (
        listing(
            retailer="Alpha Outdoors",
            url_slug="alpha-shell",
            color="Black Sapphire",
            size="M",
            current_price="300.00",
            original_price="400.00",
            stock_status="Available",
        ),
        listing(
            retailer="Alpha Outdoors",
            url_slug="alpha-shell",
            color="Dynasty",
            size="L",
            current_price="400.00",
            original_price=None,
            stock_status="Out of Stock",
        ),
        listing(
            retailer="Bravo Gear",
            url_slug="bravo-shell",
            color="Black Sapphire",
            size="M",
            current_price="280.00",
            original_price="400.00",
            stock_status="Available",
        ),
        listing(
            retailer="Alpha Outdoors",
            url_slug="alpha-shell",
            color="Black Sapphire",
            size="M",
            current_price="250.00",
            original_price="400.00",
            stock_status="Available",
            checked_at=BASE_TIME + timedelta(hours=1),
        ),
    )
    for row in rows:
        ingest_retailer_listing(session, row)


def test_search_uses_latest_snapshots_and_supports_text_search(db_session: Session) -> None:
    seed_search_data(db_session)

    result = ProductSearchService().search(
        db_session,
        ProductSearchParams(q="alpine search", limit=10),
    )

    assert result.total == 3
    assert [item.current_price for item in result.items] == [
        Decimal("250.00"),
        Decimal("280.00"),
        Decimal("400.00"),
    ]
    assert all(item.model_number == "X000066666" for item in result.items)


def test_search_combines_model_size_color_discount_and_stock_filters(
    db_session: Session,
) -> None:
    seed_search_data(db_session)

    result = ProductSearchService().search(
        db_session,
        ProductSearchParams(
            model="x000066666",
            size="medium",
            color="black sapphire",
            min_discount=Decimal("31"),
            stock_status=StockStatus.AVAILABLE,
        ),
    )

    assert result.total == 1
    assert result.items[0].retailer == "Alpha Outdoors"
    assert result.items[0].current_price == Decimal("250.00")
    assert result.items[0].discount_percentage == Decimal("37.50")
    assert result.items[0].last_checked_at == BASE_TIME + timedelta(hours=1)


def test_search_filters_out_of_stock_and_paginates(db_session: Session) -> None:
    seed_search_data(db_session)

    result = ProductSearchService().search(
        db_session,
        ProductSearchParams(
            stock_status=StockStatus.OUT_OF_STOCK,
            limit=1,
            offset=0,
        ),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].color == "Dynasty"
    assert result.items[0].size == "L"


def test_search_nonexistent_product_returns_empty_page(db_session: Session) -> None:
    seed_search_data(db_session)

    result = ProductSearchService().search(
        db_session,
        ProductSearchParams(q="nonexistent item"),
    )

    assert result.total == 0
    assert result.items == []
