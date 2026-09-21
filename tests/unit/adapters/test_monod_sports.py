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
URL = "https://www.monodsports.com/products/fixture-beta-ar-jacket"
MISSING_URL = "https://www.monodsports.com/products/missing-jacket"
CHECKED_AT = datetime(2026, 9, 20, 13, 0, tzinfo=UTC)


def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses

    def get_html(self, url: str) -> str:
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return value


def test_parse_sale_product_variants_and_partial_stock() -> None:
    rows = MonodSportsAdapter().parse_product_page(
        fixture_html(), product_url=URL, checked_at=CHECKED_AT
    )

    assert len(rows) == 3
    assert {(row.color, row.size) for row in rows} == {
        ("Stone Red", "M"),
        ("Stone Red", "L"),
        ("Lodestar", "XL"),
    }
    assert [row.stock_status for row in rows] == [
        StockStatus.AVAILABLE,
        StockStatus.OUT_OF_STOCK,
        StockStatus.AVAILABLE,
    ]
    assert all(row.current_price == Decimal("559.99") for row in rows)
    assert rows[0].original_price == Decimal("799.99")
    assert rows[0].discount_percentage == Decimal("30.00")
    assert rows[1].original_price is None
    assert all(row.style_number == "X000009906" for row in rows)


def test_regular_price_does_not_create_a_false_discount() -> None:
    html = fixture_html().replace("559.99", "799.99").replace(
        '"compare_at_price":79999', '"compare_at_price":null'
    )

    rows = MonodSportsAdapter().parse_product_page(
        html, product_url=URL, checked_at=CHECKED_AT
    )

    assert all(row.original_price is None for row in rows)
    assert all(row.discount_percentage == Decimal("0.00") for row in rows)


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
