from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.arcteryx_canada import ArcTeryxCanadaAdapter
from app.adapters.errors import AdapterParseError
from app.services.normalization import ProductGender, StockStatus

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "retailers"
    / "arcteryx_canada"
    / "product_regular.html"
)
URL = "https://arcteryx.com/ca/en/shop/mens/fixture-atom-hoody-2345"
CHECKED_AT = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_regular_product_with_partial_stock() -> None:
    rows = ArcTeryxCanadaAdapter().parse_product_page(
        fixture_html(), product_url=URL, checked_at=CHECKED_AT
    )

    assert len(rows) == 2
    assert {row.size for row in rows} == {"M", "L"}
    assert [row.stock_status for row in rows] == [
        StockStatus.AVAILABLE,
        StockStatus.OUT_OF_STOCK,
    ]
    assert all(row.current_price == Decimal("360.00") for row in rows)
    assert all(row.original_price is None for row in rows)
    assert all(row.style_number == "X000012345" for row in rows)
    assert all(row.model_name == "Fixture Atom Hoody" for row in rows)
    assert all(row.gender is ProductGender.MEN for row in rows)
    assert all(row.category == "Insulation" for row in rows)
    assert rows[0].variant_sku == "ARC-ATOM-BLK-M"
    assert str(rows[0].image_url) == "https://images.example.test/atom-black.jpg"


def test_missing_required_variant_field_is_a_parse_error() -> None:
    html = fixture_html().replace('"size": "Medium",', "", 1)

    with pytest.raises(AdapterParseError, match="variant 1 size"):
        ArcTeryxCanadaAdapter().parse_product_page(
            html, product_url=URL, checked_at=CHECKED_AT
        )


def test_broken_json_ld_is_a_parse_error() -> None:
    html = fixture_html().replace('"@context":', '"@context" invalid:', 1)

    with pytest.raises(AdapterParseError, match="invalid JSON-LD"):
        ArcTeryxCanadaAdapter().parse_product_page(
            html, product_url=URL, checked_at=CHECKED_AT
        )


def test_canada_adapter_rejects_outlet_and_query_urls() -> None:
    with pytest.raises(ValueError, match="query-free Canadian HTTPS"):
        ArcTeryxCanadaAdapter(
            product_urls=("https://outlet.arcteryx.com/ca/en/shop/mens/test",)
        )
    with pytest.raises(ValueError, match="query-free Canadian HTTPS"):
        ArcTeryxCanadaAdapter(product_urls=(f"{URL}?colour=black",))
