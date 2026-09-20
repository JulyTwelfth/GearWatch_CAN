from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.models import InventorySnapshot, PriceSnapshot
from app.services.collection_run import CollectionRunService

pytestmark = pytest.mark.integration

FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "retailers"
    / "arcteryx_outlet"
    / "product_sale.html"
)
PRODUCT_URL = "https://outlet.arcteryx.com/ca/en/shop/mens/fixture-alpine-shell-9998"
CHECKED_AT = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)


class FixtureHttpClient:
    def get_html(self, _url: str) -> str:
        return FIXTURE_PATH.read_text(encoding="utf-8")


def test_collection_run_persists_adapter_results(db_session: Session) -> None:
    adapter = ArcTeryxOutletAdapter(
        product_urls=(PRODUCT_URL,),
        http_client=FixtureHttpClient(),
        checked_at_factory=lambda: CHECKED_AT,
    )

    summary = CollectionRunService().run((adapter,), db_session)

    assert summary.status == "completed"
    assert summary.listings_processed == 3
    assert summary.price_snapshots_created == 3
    assert summary.inventory_snapshots_created == 3
    assert db_session.scalar(select(func.count()).select_from(PriceSnapshot)) == 3
    assert db_session.scalar(select(func.count()).select_from(InventorySnapshot)) == 3
