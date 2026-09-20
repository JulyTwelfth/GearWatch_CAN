from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_product_search_service
from app.main import create_app
from app.schemas.search import (
    ProductOfferRead,
    ProductSearchParams,
    ProductSearchResponse,
)
from app.services.normalization import StockStatus


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


def make_response() -> ProductSearchResponse:
    return ProductSearchResponse(
        items=[
            ProductOfferRead(
                product_id=1,
                brand="Arc'teryx",
                product_name="Fixture Search Jacket",
                model_number="X000077777",
                retailer="Fixture Retailer",
                current_price=Decimal("300.00"),
                original_price=Decimal("400.00"),
                discount_percentage=Decimal("25.00"),
                currency="CAD",
                color="Black",
                size="M",
                stock_status=StockStatus.AVAILABLE,
                product_url="https://example.invalid/fixture-search-jacket",
                last_checked_at=datetime(2026, 9, 19, 20, 0, tzinfo=UTC),
            )
        ],
        total=1,
        limit=10,
        offset=0,
    )


def make_client(service: StubSearchService) -> tuple[TestClient, FastAPI]:
    application = create_app()

    def override_session() -> object:
        return object()

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_product_search_service] = lambda: service
    return TestClient(application), application


def test_normal_search_returns_latest_offer_contract() -> None:
    service = StubSearchService(response=make_response())
    client, _ = make_client(service)

    response = client.get(
        "/api/products",
        params={
            "q": "Search Jacket",
            "size": "medium",
            "color": "black",
            "min_discount": "20",
            "stock_status": "Available",
            "limit": "10",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "product_id": 1,
                "brand": "Arc'teryx",
                "product_name": "Fixture Search Jacket",
                "model_number": "X000077777",
                "retailer": "Fixture Retailer",
                "current_price": "300.00",
                "original_price": "400.00",
                "discount_percentage": "25.00",
                "currency": "CAD",
                "color": "Black",
                "size": "M",
                "stock_status": "Available",
                "product_url": "https://example.invalid/fixture-search-jacket",
                "last_checked_at": "2026-09-19T20:00:00Z",
            }
        ],
        "total": 1,
        "limit": 10,
        "offset": 0,
    }
    assert service.params is not None
    assert service.params.size == "medium"
    assert service.params.min_discount == Decimal("20")


def test_no_matching_product_returns_empty_page() -> None:
    service = StubSearchService(
        response=ProductSearchResponse(items=[], total=0, limit=25, offset=0)
    )
    client, _ = make_client(service)

    response = client.get("/api/products", params={"q": "does-not-exist"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


@pytest.mark.parametrize(
    "query_string",
    [
        "q=",
        "q=---",
        "model=x",
        "min_discount=-1",
        "min_discount=101",
        "limit=0",
        "offset=-1",
        "unexpected=value",
    ],
)
def test_invalid_or_empty_parameters_return_422(query_string: str) -> None:
    client, _ = make_client(StubSearchService(response=make_response()))

    response = client.get(f"/api/products?{query_string}")

    assert response.status_code == 422


def test_database_error_returns_sanitized_503(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = StubSearchService(error=SQLAlchemyError("password=do-not-leak"))
    client, _ = make_client(service)

    response = client.get("/api/products", params={"q": "jacket"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "database_unavailable",
            "message": "Product search is temporarily unavailable.",
        }
    }
    assert "do-not-leak" not in response.text
    assert "do-not-leak" not in caplog.text
