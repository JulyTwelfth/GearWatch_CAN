from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.errors import AdapterParseError
from app.adapters.vpo import VpoAdapter
from app.services.normalization import StockStatus

FIXTURE = (
    Path(__file__).parents[2] / "fixtures" / "retailers" / "vpo" / "product_sale.html"
)
CATALOG_FIXTURE = FIXTURE.with_name("catalog_page.html")
URL = "https://vpo.ca/products/fixture-hat"
CHECKED_AT = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)


def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_sale_product_groups_locations_by_variant() -> None:
    rows = VpoAdapter().parse_product_page(
        fixture_html(), product_url=URL, checked_at=CHECKED_AT
    )

    assert len(rows) == 2
    assert {(row.color, row.size) for row in rows} == {
        ("Black / Cloud", "S/M"),
        ("Tatsu / Forage", "L/XL"),
    }
    assert rows[0].stock_status is StockStatus.AVAILABLE
    assert rows[1].stock_status is StockStatus.OUT_OF_STOCK
    assert all(row.current_price == Decimal("48.00") for row in rows)
    assert all(row.original_price == Decimal("60.00") for row in rows)
    assert all(row.discount_percentage == Decimal("20.00") for row in rows)
    assert all(row.style_number == "1234" for row in rows)
    assert rows[0].variant_sku == "VPO-HAT-SM"


def test_regular_product_without_compare_price_has_no_discount() -> None:
    html = fixture_html().replace(
        '"compareAtPrice":{"amount":"60.00","currencyCode":"CAD"}',
        '"compareAtPrice":null',
    )

    rows = VpoAdapter().parse_product_page(
        html, product_url=URL, checked_at=CHECKED_AT
    )

    assert all(row.original_price is None for row in rows)
    assert all(row.discount_percentage == Decimal("0.00") for row in rows)


def test_missing_offer_field_and_non_arcteryx_product_fail_loudly() -> None:
    missing_price = fixture_html().replace('"price":"48.00",', "", 1)
    with pytest.raises(AdapterParseError, match="missing current price"):
        VpoAdapter().parse_product_page(
            missing_price, product_url=URL, checked_at=CHECKED_AT
        )

    wrong_brand = fixture_html().replace('"name": "Arcteryx"', '"name": "Other"')
    with pytest.raises(AdapterParseError, match="not an Arc'teryx product"):
        VpoAdapter().parse_product_page(
            wrong_brand, product_url=URL, checked_at=CHECKED_AT
        )


def test_broken_json_ld_and_conflicting_location_prices_fail_loudly() -> None:
    no_product = fixture_html().replace('"@type": "Product"', '"@type": "Thing"', 1)
    with pytest.raises(AdapterParseError, match="missing Product JSON-LD"):
        VpoAdapter().parse_product_page(
            no_product, product_url=URL, checked_at=CHECKED_AT
        )

    conflicting = fixture_html().replace(
        '"price":"48.00","priceCurrency":"CAD","sku":"VPO-HAT-SM"',
        '"price":"49.00","priceCurrency":"CAD","sku":"VPO-HAT-SM"',
        1,
    )
    with pytest.raises(AdapterParseError, match="conflicting prices"):
        VpoAdapter().parse_product_page(
            conflicting, product_url=URL, checked_at=CHECKED_AT
        )


def test_catalog_parser_uses_collection_json_ld_and_strips_queries() -> None:
    urls = VpoAdapter().parse_catalog_page(
        CATALOG_FIXTURE.read_text(encoding="utf-8"),
        source_url="https://vpo.ca/brands/arcteryx",
    )

    assert urls == (
        "https://vpo.ca/products/alpha-jacket-mens-2",
        "https://vpo.ca/products/beta-jacket-mens-5",
    )
