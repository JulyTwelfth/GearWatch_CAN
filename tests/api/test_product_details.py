from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_product_detail_service
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
from app.services.normalization import StockStatus
from app.services.product_detail import ProductNotFoundError

CHECKED_AT = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)


class StubProductDetailService:
    def __init__(
        self,
        *,
        detail: ProductDetailResponse | None = None,
        history: ProductHistoryResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.detail = detail
        self.history = history
        self.error = error
        self.history_params: ProductHistoryParams | None = None

    def get_detail(self, _session: Session, _product_id: int) -> ProductDetailResponse:
        if self.error:
            raise self.error
        assert self.detail is not None
        return self.detail

    def get_history(
        self,
        _session: Session,
        _product_id: int,
        params: ProductHistoryParams,
    ) -> ProductHistoryResponse:
        self.history_params = params
        if self.error:
            raise self.error
        assert self.history is not None
        return self.history


def make_offer() -> CurrentProductOffer:
    return CurrentProductOffer(
        listing_id=10,
        variant_id=20,
        retailer="Fixture Retailer",
        current_price=Decimal("300.00"),
        original_price=Decimal("400.00"),
        discount_percentage=Decimal("25.00"),
        currency="CAD",
        color="Black",
        size="M",
        stock_status=StockStatus.AVAILABLE,
        product_url="https://example.invalid/detail-jacket",
        last_checked_at=CHECKED_AT,
    )


def make_detail() -> ProductDetailResponse:
    return ProductDetailResponse(
        product_id=1,
        brand="Arc'teryx",
        product_name="Fixture Detail Jacket",
        model_number="X000055555",
        last_checked_at=CHECKED_AT,
        offers=[make_offer()],
    )


def make_history() -> ProductHistoryResponse:
    return ProductHistoryResponse(
        product_id=1,
        brand="Arc'teryx",
        product_name="Fixture Detail Jacket",
        model_number="X000055555",
        limit_per_offer=10,
        offers=[
            ProductOfferHistory(
                listing_id=10,
                variant_id=20,
                retailer="Fixture Retailer",
                color="Black",
                size="M",
                product_url="https://example.invalid/detail-jacket",
                last_checked_at=CHECKED_AT,
                price_history=[
                    PriceHistoryPoint(
                        current_price=Decimal("300.00"),
                        original_price=Decimal("400.00"),
                        discount_percentage=Decimal("25.00"),
                        currency="CAD",
                        checked_at=CHECKED_AT,
                    )
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


def make_client(service: StubProductDetailService) -> tuple[TestClient, FastAPI]:
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: object()
    application.dependency_overrides[get_product_detail_service] = lambda: service
    return TestClient(application), application


def test_product_detail_returns_current_offers() -> None:
    client, _ = make_client(StubProductDetailService(detail=make_detail()))

    response = client.get("/api/products/1")

    assert response.status_code == 200
    body = response.json()
    assert body["product_name"] == "Fixture Detail Jacket"
    assert body["last_checked_at"] == "2026-09-19T20:00:00Z"
    assert body["offers"][0]["current_price"] == "300.00"
    assert body["offers"][0]["stock_status"] == "Available"


def test_product_history_returns_saved_change_points() -> None:
    service = StubProductDetailService(history=make_history())
    client, _ = make_client(service)

    response = client.get(
        "/api/products/1/history",
        params={"listing_id": 10, "variant_id": 20, "limit_per_offer": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["offers"][0]["price_history"][0]["current_price"] == "300.00"
    assert body["offers"][0]["inventory_history"][0]["stock_status"] == "Available"
    assert service.history_params == ProductHistoryParams(
        listing_id=10,
        variant_id=20,
        limit_per_offer=10,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/products/0",
        "/api/products/-1/history",
        "/api/products/1/history?listing_id=0",
        "/api/products/1/history?variant_id=-1",
        "/api/products/1/history?limit_per_offer=0",
        "/api/products/1/history?limit_per_offer=201",
        "/api/products/1/history?unexpected=value",
    ],
)
def test_detail_and_history_reject_invalid_parameters(path: str) -> None:
    client, _ = make_client(StubProductDetailService(detail=make_detail()))

    response = client.get(path)

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/products/999", "/api/products/999/history"])
def test_missing_product_returns_404(path: str) -> None:
    client, _ = make_client(
        StubProductDetailService(error=ProductNotFoundError(999))
    )

    response = client.get(path)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "product_not_found"


@pytest.mark.parametrize("path", ["/api/products/1", "/api/products/1/history"])
def test_database_failure_returns_sanitized_503(
    path: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = make_client(
        StubProductDetailService(error=SQLAlchemyError("password=do-not-leak"))
    )

    response = client.get(path)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "database_unavailable"
    assert "do-not-leak" not in response.text
    assert "do-not-leak" not in caplog.text
