from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.adapters.errors import AdapterParseError
from app.services.normalization import StockStatus

FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "retailers"
    / "arcteryx_outlet"
    / "product_sale.html"
)
PRODUCT_URL = "https://outlet.arcteryx.com/ca/en/shop/mens/fixture-alpine-shell-9998"
CHECKED_AT = datetime(2026, 9, 19, 18, 0, tzinfo=UTC)


def read_fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


class FakeHtmlClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls: list[str] = []

    def get_html(self, url: str) -> str:
        self.calls.append(url)
        return self.html


def test_parse_sale_fixture_returns_one_listing_per_variant() -> None:
    listings = ArcTeryxOutletAdapter().parse_product_page(
        read_fixture(), product_url=PRODUCT_URL, checked_at=CHECKED_AT
    )

    assert len(listings) == 3
    assert {listing.size for listing in listings} == {"M", "L", "XL"}
    assert {listing.color for listing in listings} == {
        "Black Sapphire",
        "24K Black",
        "Dynasty",
    }
    assert [listing.stock_status for listing in listings] == [
        StockStatus.AVAILABLE,
        StockStatus.OUT_OF_STOCK,
        StockStatus.AVAILABLE,
    ]
    assert all(listing.brand == "Arc'teryx" for listing in listings)
    assert all(listing.retailer == "Arc'teryx Outlet Canada" for listing in listings)
    assert all(listing.model_number == "X000099998" for listing in listings)
    assert all(listing.current_price == Decimal("315.00") for listing in listings)
    assert all(listing.original_price == Decimal("450.00") for listing in listings)
    assert all(listing.discount_percentage == Decimal("30.00") for listing in listings)
    assert all(listing.checked_at == CHECKED_AT for listing in listings)


def test_collect_fetches_only_configured_product_urls() -> None:
    client = FakeHtmlClient(read_fixture())
    adapter = ArcTeryxOutletAdapter(
        product_urls=(PRODUCT_URL,),
        http_client=client,
        checked_at_factory=lambda: CHECKED_AT,
    )

    listings = adapter.collect()

    assert len(listings) == 3
    assert client.calls == [PRODUCT_URL]


@pytest.mark.parametrize(
    "url",
    [
        "http://outlet.arcteryx.com/ca/en/shop/mens/product",
        "https://example.com/ca/en/shop/mens/product",
        "https://outlet.arcteryx.com/ca/en/cart",
        "https://outlet.arcteryx.com/ca/en/shop/mens/product?search=secret",
    ],
)
def test_non_product_or_non_official_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="query-free Canadian HTTPS product pages"):
        ArcTeryxOutletAdapter(product_urls=(url,))


def test_missing_application_state_keeps_original_price_unknown() -> None:
    html = read_fixture().replace(
        '<script id="__NEXT_DATA__" type="application/json">',
        '<script id="removed-next-data" type="application/json">',
    )

    listings = ArcTeryxOutletAdapter().parse_product_page(
        html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
    )

    assert all(listing.original_price is None for listing in listings)
    assert all(listing.discount_percentage == Decimal("0.00") for listing in listings)


def test_non_sale_original_price_is_not_duplicated() -> None:
    html = read_fixture().replace('\\"price\\":450', '\\"price\\":315')

    listings = ArcTeryxOutletAdapter().parse_product_page(
        html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
    )

    assert all(listing.original_price is None for listing in listings)


def test_unrecognized_schema_availability_maps_to_unknown() -> None:
    html = read_fixture().replace(
        "https://schema.org/LimitedAvailability",
        "https://schema.org/PreOrder",
    )

    listings = ArcTeryxOutletAdapter().parse_product_page(
        html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
    )

    assert listings[2].stock_status is StockStatus.UNKNOWN


def test_missing_product_group_fails_loudly() -> None:
    html = read_fixture().replace('"@type": "ProductGroup"', '"@type": "Thing"')

    with pytest.raises(AdapterParseError, match="missing ProductGroup JSON-LD"):
        ArcTeryxOutletAdapter().parse_product_page(
            html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
        )


def test_missing_variant_field_identifies_variant() -> None:
    html = read_fixture().replace('"color": "Black Sapphire",', "", 1)

    with pytest.raises(AdapterParseError, match="variant 1 color"):
        ArcTeryxOutletAdapter().parse_product_page(
            html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
        )


def test_invalid_application_state_json_fails_loudly() -> None:
    html = read_fixture().replace('"props": {', '"props": invalid,', 1)

    with pytest.raises(AdapterParseError, match="__NEXT_DATA__ is invalid JSON"):
        ArcTeryxOutletAdapter().parse_product_page(
            html, product_url=PRODUCT_URL, checked_at=CHECKED_AT
        )
