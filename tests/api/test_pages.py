from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db_session,
    get_product_detail_service,
    get_product_search_service,
)
from app.main import create_app
from app.schemas.product_detail import (
    CurrentProductOffer,
    InventoryHistoryPoint,
    PriceHistoryPoint,
    ProductDetailResponse,
    ProductHistoryParams,
    ProductHistoryResponse,
    ProductOfferHistory,
)
from app.schemas.search import (
    ProductOfferRead,
    ProductSearchParams,
    ProductSearchResponse,
)
from app.services.normalization import StockStatus
from app.services.product_detail import ProductNotFoundError

CHECKED_AT = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
PRODUCT_URL = "https://example.invalid/fixture-shell"


class StubSearchService:
    def __init__(
        self,
        response: ProductSearchResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.params: ProductSearchParams | None = None

    def search(
        self,
        _session: Session,
        params: ProductSearchParams,
    ) -> ProductSearchResponse:
        self.params = params
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


class StubDetailService:
    def __init__(
        self,
        detail: ProductDetailResponse | None = None,
        history: ProductHistoryResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail = detail
        self.history = history
        self.error = error

    def get_detail(self, _session: Session, _product_id: int) -> ProductDetailResponse:
        if self.error:
            raise self.error
        assert self.detail is not None
        return self.detail

    def get_history(
        self,
        _session: Session,
        _product_id: int,
        _params: ProductHistoryParams,
    ) -> ProductHistoryResponse:
        if self.error:
            raise self.error
        assert self.history is not None
        return self.history


def search_response(*, items: bool = True) -> ProductSearchResponse:
    offers = []
    if items:
        offers.append(
            ProductOfferRead(
                product_id=1,
                brand="Arc'teryx",
                product_name="Fixture Alpine Shell",
                model_number="X000044444",
                retailer="Fixture Retailer",
                current_price=Decimal("300.00"),
                original_price=Decimal("400.00"),
                discount_percentage=Decimal("25.00"),
                currency="CAD",
                color="Black Sapphire",
                size="M",
                stock_status=StockStatus.AVAILABLE,
                product_url=PRODUCT_URL,
                last_checked_at=CHECKED_AT,
            )
        )
    return ProductSearchResponse(items=offers, total=len(offers), limit=100, offset=0)


def detail_response() -> ProductDetailResponse:
    return ProductDetailResponse(
        product_id=1,
        brand="Arc'teryx",
        product_name="Fixture Alpine Shell",
        model_number="X000044444",
        last_checked_at=CHECKED_AT,
        offers=[
            CurrentProductOffer(
                listing_id=10,
                variant_id=20,
                retailer="Fixture Retailer",
                current_price=Decimal("300.00"),
                original_price=Decimal("400.00"),
                discount_percentage=Decimal("25.00"),
                currency="CAD",
                color="Black Sapphire",
                size="M",
                stock_status=StockStatus.AVAILABLE,
                product_url=PRODUCT_URL,
                last_checked_at=CHECKED_AT,
            )
        ],
    )


def history_response() -> ProductHistoryResponse:
    return ProductHistoryResponse(
        product_id=1,
        brand="Arc'teryx",
        product_name="Fixture Alpine Shell",
        model_number="X000044444",
        limit_per_offer=50,
        offers=[
            ProductOfferHistory(
                listing_id=10,
                variant_id=20,
                retailer="Fixture Retailer",
                color="Black Sapphire",
                size="M",
                product_url=PRODUCT_URL,
                last_checked_at=CHECKED_AT,
                price_history=[
                    PriceHistoryPoint(
                        current_price=Decimal("350.00"),
                        original_price=Decimal("400.00"),
                        discount_percentage=Decimal("12.50"),
                        currency="CAD",
                        checked_at=CHECKED_AT,
                    ),
                    PriceHistoryPoint(
                        current_price=Decimal("300.00"),
                        original_price=Decimal("400.00"),
                        discount_percentage=Decimal("25.00"),
                        currency="CAD",
                        checked_at=CHECKED_AT,
                    ),
                ],
                inventory_history=[
                    InventoryHistoryPoint(
                        stock_status=StockStatus.AVAILABLE,
                        checked_at=CHECKED_AT,
                    )
                ],
            )
        ],
    )


def client_with_services(
    *,
    search_service: StubSearchService | None = None,
    detail_service: StubDetailService | None = None,
) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: object()
    if search_service is not None:
        application.dependency_overrides[get_product_search_service] = lambda: search_service
    if detail_service is not None:
        application.dependency_overrides[get_product_detail_service] = lambda: detail_service
    return TestClient(application)


def test_search_page_renders_filters_results_and_freshness_notice() -> None:
    service = StubSearchService(response=search_response())
    client = client_with_services(search_service=service)

    response = client.get(
        "/",
        params={
            "q": "Alpine Shell",
            "size": "medium",
            "color": "Black Sapphire",
            "min_discount": "20",
            "stock_status": "Available",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Fixture Alpine Shell" in response.text
    assert 'href="/products/1"' in response.text
    assert "Last checked:" in response.text
    assert "periodically collected, not real-time" in response.text
    assert "Confirm final price and availability" in response.text
    assert service.params is not None
    assert service.params.size == "medium"
    assert service.params.min_discount == Decimal("20")


def test_search_page_renders_no_results_state() -> None:
    client = client_with_services(
        search_service=StubSearchService(response=search_response(items=False))
    )

    response = client.get("/", params={"q": "not collected"})

    assert response.status_code == 200
    assert "No matching saved offers" in response.text
    assert "Last checked:" in response.text


def test_search_page_renders_html_validation_error() -> None:
    client = client_with_services(
        search_service=StubSearchService(response=search_response())
    )

    response = client.get("/", params={"q": "---"})

    assert response.status_code == 422
    assert "Invalid search filters" in response.text
    assert "Last checked:" in response.text


def test_product_page_renders_offers_history_chart_and_retailer_link() -> None:
    client = client_with_services(
        detail_service=StubDetailService(
            detail=detail_response(),
            history=history_response(),
        )
    )

    response = client.get("/products/1")

    assert response.status_code == 200
    assert "Current saved offers" in response.text
    assert "Price and inventory history" in response.text
    assert 'data-values="350.00,300.00"' in response.text
    assert f'href="{PRODUCT_URL}"' in response.text
    assert 'target="_blank" rel="noopener noreferrer"' in response.text
    assert "Last checked:" in response.text


@pytest.mark.parametrize("path", ["/products/999", "/products/not-a-number"])
def test_product_page_renders_not_found_page(path: str) -> None:
    client = client_with_services(
        detail_service=StubDetailService(error=ProductNotFoundError(999))
    )

    response = client.get(path)

    assert response.status_code == 404
    assert "Product not found" in response.text
    assert "Return to search" in response.text


@pytest.mark.parametrize("path", ["/", "/products/1"])
def test_pages_render_sanitized_database_error(
    path: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_error = SQLAlchemyError("password=do-not-leak")
    client = client_with_services(
        search_service=StubSearchService(error=secret_error),
        detail_service=StubDetailService(error=secret_error),
    )

    response = client.get(path)

    assert response.status_code == 503
    assert "temporarily unavailable" in response.text
    assert "do-not-leak" not in response.text
    assert "do-not-leak" not in caplog.text


def test_static_stylesheet_is_served() -> None:
    client = client_with_services(
        search_service=StubSearchService(response=search_response())
    )

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--pine" in response.text
