from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.errors import AdapterParseError
from app.adapters.the_outfitters import TheOutfittersAdapter
from app.core.http import HttpFetchError
from app.services.normalization import SourceStatus, StockStatus

FIXTURE_DIR = (
    Path(__file__).parents[2] / "fixtures" / "retailers" / "the_outfitters"
)
PRODUCT_FIXTURE = FIXTURE_DIR / "product_sale.json"
CATALOG_FIXTURE = FIXTURE_DIR / "catalog_page.json"
URL = (
    "https://theoutfitters.nf.ca/products/"
    "arcteryx-mens-beta-jacket-x000010511"
)
CATALOG_URL = (
    "https://theoutfitters.nf.ca/collections/arcteryx/products.json"
    "?limit=50&page=1"
)
CHECKED_AT = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def fixture(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses

    def _get(self, url: str) -> str:
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return value

    def get_html(self, url: str) -> str:
        return self._get(url)

    def get_json(self, url: str) -> str:
        return self._get(url)

    def get_xml(self, url: str) -> str:
        return self._get(url)


def test_parse_product_variants_sale_stock_and_missing_sku_fallback() -> None:
    rows = TheOutfittersAdapter().parse_product_page(
        fixture(PRODUCT_FIXTURE), product_url=URL, checked_at=CHECKED_AT
    )

    assert len(rows) == 3
    assert {(row.color, row.size) for row in rows} == {
        ("Black", "S"),
        ("Blaze", "M"),
        ("Black", "L"),
    }
    assert rows[0].stock_status is StockStatus.AVAILABLE
    assert rows[1].stock_status is StockStatus.OUT_OF_STOCK
    assert rows[2].stock_status is StockStatus.UNKNOWN
    assert rows[0].current_price == Decimal("500.00")
    assert rows[0].original_price is None
    assert rows[1].current_price == Decimal("400.00")
    assert rows[1].original_price == Decimal("500.00")
    assert rows[1].discount_percentage == Decimal("20.00")
    assert rows[2].variant_sku == "shopify:103"
    assert all(row.style_number == "X000010511" for row in rows)
    assert all(row.product_name == "Arc'teryx Beta Jacket Men's" for row in rows)


def test_fetch_product_reads_the_public_shopify_json_resource() -> None:
    adapter = TheOutfittersAdapter(
        http_client=FakeClient({f"{URL}.js": fixture(PRODUCT_FIXTURE)}),
        checked_at_factory=lambda: CHECKED_AT,
    )

    rows = adapter.fetch_product(URL)

    assert len(rows) == 3
    assert all(row.checked_at == CHECKED_AT for row in rows)


def test_catalog_parsing_filters_brand_and_discovery_deduplicates_style() -> None:
    adapter = TheOutfittersAdapter(
        discovery_enabled=True,
        discovery_max_products=2,
        discovery_max_pages=1,
        http_client=FakeClient({CATALOG_URL: fixture(CATALOG_FIXTURE)}),
        checked_at_factory=lambda: CHECKED_AT,
    )

    product_urls, failures, statuses = adapter._collection_plan()

    assert product_urls == (
        URL,
        "https://theoutfitters.nf.ca/products/"
        "arcteryx-mens-atom-hoody-x000009556",
    )
    assert failures == ()
    assert statuses[0].status is SourceStatus.SUCCESS
    assert len(adapter.discovered_product_urls) == 2


def test_malformed_catalogue_payloads_fail_loudly() -> None:
    adapter = TheOutfittersAdapter()

    with pytest.raises(AdapterParseError, match="invalid"):
        adapter.parse_catalog_page("{", source_url=CATALOG_URL)
    with pytest.raises(AdapterParseError, match="missing products"):
        adapter.parse_catalog_page("{}", source_url=CATALOG_URL)


def test_catalog_pagination_is_bounded_and_blocked_page_is_reported() -> None:
    adapter = TheOutfittersAdapter(
        discovery_enabled=True,
        discovery_max_pages=1,
        http_client=FakeClient(
            {
                CATALOG_URL: HttpFetchError(
                    "HTTP 403", url=CATALOG_URL, status_code=403
                )
            }
        ),
        checked_at_factory=lambda: CHECKED_AT,
    )

    product_urls, failures, statuses = adapter._collection_plan()

    assert product_urls == ()
    assert len(adapter.catalog_requests()) == 1
    assert failures[0].status is SourceStatus.BLOCKED
    assert statuses[0].status is SourceStatus.BLOCKED


def test_malformed_product_and_missing_fields_fail_loudly() -> None:
    adapter = TheOutfittersAdapter()
    with pytest.raises(AdapterParseError, match="invalid"):
        adapter.parse_product_page("{", product_url=URL, checked_at=CHECKED_AT)
    with pytest.raises(AdapterParseError, match="not an object"):
        adapter.parse_product_page("[]", product_url=URL, checked_at=CHECKED_AT)

    missing_price = fixture(PRODUCT_FIXTURE).replace('"price": 50000,', "", 1)
    with pytest.raises(AdapterParseError, match="missing price"):
        adapter.parse_product_page(
            missing_price, product_url=URL, checked_at=CHECKED_AT
        )

    missing_style = fixture(PRODUCT_FIXTURE).replace("X000010511", "NO-STYLE")
    with pytest.raises(AdapterParseError, match="missing its style number"):
        adapter.parse_product_page(
            missing_style,
            product_url="https://theoutfitters.nf.ca/products/no-style",
            checked_at=CHECKED_AT,
        )

    wrong_vendor = fixture(PRODUCT_FIXTURE).replace("ARC'TERYX", "Other Brand", 1)
    with pytest.raises(AdapterParseError, match="not an Arc'teryx product"):
        adapter.parse_product_page(
            wrong_vendor, product_url=URL, checked_at=CHECKED_AT
        )


def test_invalid_product_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="query-free"):
        TheOutfittersAdapter(
            product_urls=(
                "https://theoutfitters.nf.ca/products/beta?variant=secret",
            )
        )
