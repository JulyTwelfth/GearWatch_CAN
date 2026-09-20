from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.adapters.base import RetailerAdapter
from app.repositories import IngestResult
from app.schemas.retailer import RetailerListing
from app.services.collection_run import CollectionRunService


def make_listing(retailer: str) -> RetailerListing:
    return RetailerListing.model_validate(
        {
            "brand": "Arc'teryx",
            "product_name": "Fixture Collection Jacket",
            "model_number": "X000088888",
            "retailer": retailer,
            "current_price": "280.00",
            "original_price": "400.00",
            "currency": "CAD",
            "color": "Black",
            "size": "M",
            "stock_status": "Available",
            "product_url": f"https://example.invalid/{retailer.casefold().replace(' ', '-')}",
            "checked_at": datetime(2026, 9, 19, 20, 0, tzinfo=UTC),
        }
    )


class SuccessfulAdapter(RetailerAdapter):
    def __init__(self, retailer_name: str) -> None:
        self.retailer_name = retailer_name

    def collect(self) -> Sequence[RetailerListing]:
        return (make_listing(self.retailer_name),)


class FailedAdapter(RetailerAdapter):
    retailer_name = "Failed Retailer"

    def collect(self) -> Sequence[RetailerListing]:
        raise TimeoutError("fixture timeout")


def make_ingest_result(position: int) -> IngestResult:
    return IngestResult(
        product_id=position,
        retailer_id=position,
        listing_id=position,
        variant_id=position,
        price_snapshot_created=True,
        inventory_snapshot_created=position == 1,
    )


def test_run_persists_successes_and_reports_partial_failure() -> None:
    written: list[RetailerListing] = []

    def writer(_session: Session, listing: RetailerListing) -> IngestResult:
        written.append(listing)
        return make_ingest_result(len(written))

    summary = CollectionRunService(listing_writer=writer).run(
        (
            SuccessfulAdapter("First Retailer"),
            FailedAdapter(),
            SuccessfulAdapter("Second Retailer"),
        ),
        object(),  # type: ignore[arg-type]
    )

    assert [listing.retailer for listing in written] == [
        "First Retailer",
        "Second Retailer",
    ]
    assert summary.status == "partial_failure"
    assert summary.configured_retailers == (
        "First Retailer",
        "Failed Retailer",
        "Second Retailer",
    )
    assert summary.successful_retailers == ("First Retailer", "Second Retailer")
    assert summary.listings_processed == 2
    assert summary.price_snapshots_created == 2
    assert summary.inventory_snapshots_created == 1
    assert summary.failures[0].error_type == "TimeoutError"


def test_database_error_propagates_to_transaction_owner() -> None:
    def failing_writer(_session: Session, _listing: RetailerListing) -> IngestResult:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        CollectionRunService(listing_writer=failing_writer).run(
            (SuccessfulAdapter("Working Retailer"),),
            object(),  # type: ignore[arg-type]
        )
