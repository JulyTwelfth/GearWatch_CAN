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


def test_search_and_detail_pages_render_postgresql_data(db_session: Session) -> None:
    seed_search_data(db_session)
    product_id = db_session.scalar(
        select(Product.id).where(Product.normalized_model_number == "x000066666")
    )
    application = create_app()

    def override_session() -> Iterator[Session]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    client = TestClient(application)

    search_response = client.get(
        "/",
        params={
            "model": "X000066666",
            "size": "M",
            "stock_status": "Available",
        },
    )
    detail_response = client.get(f"/products/{product_id}")

    assert search_response.status_code == 200
    assert "Fixture Alpine Search Shell" in search_response.text
    assert f'href="/products/{product_id}"' in search_response.text
    assert detail_response.status_code == 200
    assert "Alpha Outdoors" in detail_response.text
    assert "Bravo Gear" in detail_response.text
    assert "Price and inventory history" in detail_response.text
    assert "300.00,250.00" in detail_response.text
