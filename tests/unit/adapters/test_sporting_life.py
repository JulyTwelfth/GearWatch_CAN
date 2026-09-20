from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters import AdapterParseError, FixturePage, SportingLifeAdapter
from app.services.normalization import StockStatus

FIXTURE_DIRECTORY = (
    Path(__file__).parents[2] / "fixtures" / "retailers" / "sporting_life"
)
CHECKED_AT = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)


def read_fixture(filename: str) -> str:
    return (FIXTURE_DIRECTORY / filename).read_text(encoding="utf-8")


def test_parse_sale_fixture_returns_one_listing_per_variant() -> None:
    adapter = SportingLifeAdapter()

    listings = adapter.parse_product_page(
        read_fixture("product_sale.html"),
        product_url="https://example.invalid/sporting-life/fixture-test-shell",
        checked_at=CHECKED_AT,
    )

    assert len(listings) == 3
    assert {listing.size for listing in listings} == {"M", "L", "XL"}
    assert {listing.color for listing in listings} == {"Black Sapphire", "24K Black"}
    assert {listing.stock_status for listing in listings} == {
        StockStatus.AVAILABLE,
        StockStatus.OUT_OF_STOCK,
        StockStatus.UNKNOWN,
    }
    assert all(listing.brand == "Arc'teryx" for listing in listings)
    assert all(listing.model_number == "X000099999" for listing in listings)
    assert all(listing.current_price == Decimal("300.00") for listing in listings)
    assert all(listing.original_price == Decimal("400.00") for listing in listings)
    assert all(listing.discount_percentage == Decimal("25.00") for listing in listings)
    assert all(listing.checked_at == CHECKED_AT for listing in listings)


def test_parse_regular_price_fixture_allows_missing_original_price() -> None:
    adapter = SportingLifeAdapter()

    listings = adapter.parse_product_page(
        read_fixture("product_regular.html"),
        product_url="https://example.invalid/sporting-life/fixture-test-pack",
        checked_at=CHECKED_AT,
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.product_name == "Arc'teryx Fixture Test Pack"
    assert listing.original_price is None
    assert listing.discount_percentage == Decimal("0.00")
    assert listing.size == "ONE SIZE"
    assert listing.stock_status is StockStatus.AVAILABLE


def test_collect_parses_all_configured_local_pages() -> None:
    adapter = SportingLifeAdapter(
        pages=(
            FixturePage(
                html=read_fixture("product_sale.html"),
                product_url="https://example.invalid/sporting-life/fixture-test-shell",
                checked_at=CHECKED_AT,
            ),
            FixturePage(
                html=read_fixture("product_regular.html"),
                product_url="https://example.invalid/sporting-life/fixture-test-pack",
                checked_at=CHECKED_AT,
            ),
        )
    )

    assert len(adapter.collect()) == 4


def test_structure_change_missing_product_root_fails_loudly() -> None:
    changed_html = read_fixture("product_sale.html").replace(
        "data-product-detail", "data-renamed-product-detail", 1
    )

    with pytest.raises(AdapterParseError, match="missing the product detail root"):
        SportingLifeAdapter().parse_product_page(
            changed_html,
            product_url="https://example.invalid/changed-structure",
            checked_at=CHECKED_AT,
        )


def test_structure_change_missing_variant_field_identifies_variant() -> None:
    changed_html = read_fixture("product_sale.html").replace(
        'data-size="medium"', "", 1
    )

    with pytest.raises(AdapterParseError, match="variant 1 size"):
        SportingLifeAdapter().parse_product_page(
            changed_html,
            product_url="https://example.invalid/changed-variant",
            checked_at=CHECKED_AT,
        )


def test_structure_change_missing_current_price_fails_loudly() -> None:
    changed_html = read_fixture("product_sale.html").replace(
        "data-current-price", "data-renamed-current-price", 1
    )

    with pytest.raises(AdapterParseError, match="missing current price"):
        SportingLifeAdapter().parse_product_page(
            changed_html,
            product_url="https://example.invalid/changed-price",
            checked_at=CHECKED_AT,
        )
