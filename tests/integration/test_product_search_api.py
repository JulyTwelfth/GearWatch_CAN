from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.main import create_app
from app.models import Product
from tests.integration.test_product_search import seed_search_data

pytestmark = pytest.mark.integration


def test_search_api_queries_postgresql(db_session: Session) -> None:
    seed_search_data(db_session)
    application = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session

    response = TestClient(application).get(
        "/api/products",
        params={
            "model": "X000066666",
            "size": "M",
            "color": "Black Sapphire",
            "min_discount": "31",
            "stock_status": "Available",
            "category": "Jackets",
            "gender": "Men",
            "retailer": "Alpha Outdoors",
            "sort": "price_asc",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["retailer"] == "Alpha Outdoors"
    assert body["items"][0]["current_price"] == "250.00"
    assert body["items"][0]["source_status"] == "success"
    assert body["items"][0]["last_checked_at"] == "2026-09-19T21:00:00Z"


def test_detail_and_history_apis_query_postgresql(db_session: Session) -> None:
    seed_search_data(db_session)
    product_id = db_session.scalar(
        select(Product.id).where(Product.normalized_model_number == "x000066666")
    )
    application = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    client = TestClient(application)

    detail_response = client.get(f"/api/products/{product_id}")
    history_response = client.get(
        f"/api/products/{product_id}/history",
        params={"limit_per_offer": 10},
    )

    assert detail_response.status_code == 200
    assert len(detail_response.json()["offers"]) == 3
    assert history_response.status_code == 200
    assert len(history_response.json()["offers"]) == 3
