from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.retailer import RetailerListing
from app.services.normalization import StockStatus


def make_listing(**overrides: object) -> RetailerListing:
    data: dict[str, object] = {
        "brand": "Arc’teryx",
        "product_name": "  ARC TERYX   Beta Jacket - Men's ",
        "model_number": "x000009859",
        "retailer": " MEC ",
        "current_price": "CAD $375.00",
        "original_price": "$500.00",
        "currency": "cad",
        "color": "black sapphire",
        "size": "medium",
        "stock_status": "in stock",
        "product_url": "https://www.example.com/products/beta-jacket",
        "checked_at": datetime(2026, 9, 19, 12, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return RetailerListing.model_validate(data)


def test_retailer_listing_normalizes_adapter_output() -> None:
    listing = make_listing()

    assert listing.brand == "Arc'teryx"
    assert listing.product_name == "Arc'teryx Beta Jacket - Men's"
    assert listing.model_number == "X000009859"
    assert listing.retailer == "MEC"
    assert listing.current_price == Decimal("375.00")
    assert listing.original_price == Decimal("500.00")
    assert listing.discount_percentage == Decimal("25.00")
    assert listing.currency == "CAD"
    assert listing.color == "Black Sapphire"
    assert listing.size == "M"
    assert listing.stock_status is StockStatus.AVAILABLE
    assert listing.checked_at.tzinfo is UTC


def test_retailer_listing_requires_timezone_aware_checked_at() -> None:
    with pytest.raises(ValidationError, match="checked_at must include a timezone"):
        make_listing(checked_at=datetime(2026, 9, 19, 12, 30))


def test_retailer_listing_rejects_original_price_below_current_price() -> None:
    with pytest.raises(ValidationError, match="original price cannot be lower"):
        make_listing(current_price="$500", original_price="$400")


def test_retailer_listing_does_not_trust_supplied_discount() -> None:
    listing = make_listing(discount_percentage="99")

    assert listing.discount_percentage == Decimal("25.00")


def test_retailer_listing_rejects_unknown_adapter_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        make_listing(unexpected_field="schema drift")


def test_retailer_listing_rejects_empty_brand() -> None:
    with pytest.raises(ValidationError, match="brand cannot be empty"):
        make_listing(brand="  ")
