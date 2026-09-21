from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.base import AdapterFetchStatus
from app.adapters.errors import AdapterParseError
from app.adapters.monod_sports import MonodSportsAdapter
from app.core.http import HttpFetchError
from app.services.normalization import SourceStatus, StockStatus

FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "retailers"
    / "monod_sports"
    / "product_sale.html"
)
JSON_FIXTURE = FIXTURE.with_suffix(".json")
CATALOG_FIXTURE = FIXTURE.with_name("catalog_page.json")
URL = "https://www.monodsports.com/products/fixture-beta-ar-jacket"
JSON_URL = f"{URL}.js"
MISSING_URL = "https://www.monodsports.com/products/missing-jacket"
CHECKED_AT = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)


def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def fixture_json() -> str:
    return JSON_FIXTURE.read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses

    def get_html(self, url: str) -> str:
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return value

    def get_json(self, url: str) -> str:
        return self.get_html(url)


def test_parse_sale_product_variants_and_partial_stock() -> None:
    rows = MonodSportsAdapter().parse_product_page(
        fixture_html(),
        product_url=URL,
        checked_at=CHECKED_AT,
        product_json=fixture_json(),
    )

    assert len(rows) == 3
    assert {(row.color, row.size) for row in rows} == {
        ("Stone Red", "S"),
        ("Stone Red", "M"),
        ("Lodestar", "XL"),
    }
    assert [row.stock_status for row in rows] == [
        StockStatus.OUT_OF_STOCK,
        StockStatus.AVAILABLE,
        StockStatus.AVAILABLE,
    ]
    assert all(row.current_price == Decimal("559.99") for row in rows)
    assert all(row.original_price == Decimal("799.99") for row in rows)
    assert all(row.discount_percentage == Decimal("30.00") for row in rows)
    assert all(row.style_number == "X000009906" for row in rows)


def test_regular_price_does_not_create_a_false_discount() -> None:
    product_json = fixture_json().replace('"price": 55999', '"price": 79999').replace(
        '"compare_at_price": 79999', '"compare_at_price": null'
    )

    rows = MonodSportsAdapter().parse_product_page(
        fixture_html(),
        product_url=URL,
        checked_at=CHECKED_AT,
        product_json=product_json,
    )

    assert all(row.original_price is None for row in rows)
    assert all(row.discount_percentage == Decimal("0.00") for row in rows)


def test_hidden_sold_out_colour_and_malformed_product_json_are_not_silently_used() -> None:
    rows = MonodSportsAdapter().parse_product_page(
        fixture_html(),
        product_url=URL,
        checked_at=CHECKED_AT,
        product_json=fixture_json(),
    )
    assert "Black Sapphire" not in {row.color for row in rows}

    with pytest.raises(AdapterParseError, match="missing price"):
        MonodSportsAdapter().parse_product_page(
            fixture_html(),
            product_url=URL,
            checked_at=CHECKED_AT,
            product_json=fixture_json().replace('"price": 55999,', "", 1),
        )


def test_single_colour_product_can_fall_back_when_colour_controls_are_absent() -> None:
    no_controls = fixture_html().replace("data-monod-size-color-tab", "data-other-tab")
    single_colour_json = fixture_json().replace(
        "Stone Red", "Lodestar"
    ).replace("Black Sapphire", "Lodestar")

    rows = MonodSportsAdapter().parse_product_page(
        no_controls,
        product_url=URL,
        checked_at=CHECKED_AT,
        product_json=single_colour_json,
    )

    assert len(rows) == 4
    assert {row.color for row in rows} == {"Lodestar"}


def test_multi_colour_product_without_colour_controls_fails_loudly() -> None:
    no_controls = fixture_html().replace("data-monod-size-color-tab", "data-other-tab")

    with pytest.raises(AdapterParseError, match="missing active colour controls"):
        MonodSportsAdapter().parse_product_page(
            no_controls,
            product_url=URL,
            checked_at=CHECKED_AT,
            product_json=fixture_json(),
        )


def test_colour_only_shopify_product_is_saved_as_one_size() -> None:
    no_controls = fixture_html().replace("data-monod-size-color-tab", "data-other-tab")
    product_json = """{
      "options": [{"name": "Colour", "position": 1, "values": ["Black"]}],
      "variants": [{
        "id": 501, "option1": "Black", "option2": null,
        "sku": "MON-PACK-BLK", "available": true,
        "price": 24999, "compare_at_price": null
      }]
    }"""

    rows = MonodSportsAdapter().parse_product_page(
        no_controls,
        product_url=URL,
        checked_at=CHECKED_AT,
        product_json=product_json,
    )

    assert len(rows) == 1
    assert rows[0].color == "Black"
    assert rows[0].size == "ONE SIZE"
    assert rows[0].stock_status is StockStatus.AVAILABLE


def test_missing_variant_sku_and_broken_structure_fail_loudly() -> None:
    missing_sku = fixture_html().replace('"sku": "MON-BETA-M",', "", 1)
    with pytest.raises(AdapterParseError, match="variant 1 SKU"):
        MonodSportsAdapter().parse_product_page(
            missing_sku, product_url=URL, checked_at=CHECKED_AT
        )

    no_product = fixture_html().replace('"@type": "ProductGroup"', '"@type": "Thing"')
    with pytest.raises(AdapterParseError, match="missing ProductGroup"):
        MonodSportsAdapter().parse_product_page(
            no_product, product_url=URL, checked_at=CHECKED_AT
        )


def test_collect_maps_404_and_timeout_to_unavailable_without_discarding_success() -> None:
    timeout_url = "https://www.monodsports.com/products/timed-out-jacket"
    adapter = MonodSportsAdapter(
        product_urls=(MISSING_URL, timeout_url, URL),
        http_client=FakeClient(
            {
                MISSING_URL: HttpFetchError(
                    "HTTP 404", url=MISSING_URL, status_code=404
                ),
                timeout_url: HttpFetchError("timeout", url=timeout_url),
                URL: fixture_html(),
                JSON_URL: fixture_json(),
            }
        ),
        checked_at_factory=lambda: CHECKED_AT,
    )

    rows = adapter.collect()

    assert len(rows) == 3
    assert [failure.status for failure in adapter.item_failures] == [
        SourceStatus.UNAVAILABLE,
        SourceStatus.UNAVAILABLE,
    ]
    assert adapter.fetch_statuses[-1] == AdapterFetchStatus(
        resource=URL,
        status=SourceStatus.SUCCESS,
        checked_at=CHECKED_AT,
    )


def test_collect_maps_403_to_blocked() -> None:
    adapter = MonodSportsAdapter(
        product_urls=(URL,),
        http_client=FakeClient(
            {URL: HttpFetchError("HTTP 403", url=URL, status_code=403)}
        ),
        checked_at_factory=lambda: CHECKED_AT,
    )

    assert adapter.collect() == []
    assert adapter.item_failures[0].status is SourceStatus.BLOCKED
    assert adapter.fetch_statuses[0].status is SourceStatus.BLOCKED


def test_catalog_parser_filters_non_arcteryx_products_and_prioritizes_comparisons() -> None:
    adapter = MonodSportsAdapter()
    urls = adapter.parse_catalog_page(
        CATALOG_FIXTURE.read_text(encoding="utf-8"),
        source_url="https://www.monodsports.com/collections/arcteryx/products.json",
    )

    assert set(urls) == {
        "https://www.monodsports.com/products/mens-atom-hoody",
        "https://www.monodsports.com/products/mens-beta-sl-jacket",
    }
    assert adapter.prioritize_discovered_urls(urls)[0].endswith(
        "/mens-beta-sl-jacket"
    )
