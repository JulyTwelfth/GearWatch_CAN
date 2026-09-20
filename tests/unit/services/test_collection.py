import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.adapters.base import RetailerAdapter
from app.core.http import HttpFetchError
from app.schemas.retailer import RetailerListing
from app.services.collection import CollectionService


def make_listing(retailer: str = "Working Retailer") -> RetailerListing:
    return RetailerListing.model_validate(
        {
            "brand": "Arc'teryx",
            "product_name": "Arc'teryx Fixture Test Jacket",
            "model_number": "X000077777",
            "retailer": retailer,
            "current_price": "300.00",
            "original_price": "400.00",
            "currency": "CAD",
            "color": "Black",
            "size": "M",
            "stock_status": "Available",
            "product_url": "https://example.invalid/product",
            "checked_at": datetime(2026, 9, 19, 16, 0, tzinfo=UTC),
        }
    )


class SuccessfulAdapter(RetailerAdapter):
    retailer_name = "Working Retailer"

    def collect(self) -> Sequence[RetailerListing]:
        return (make_listing(self.retailer_name),)


class EmptyAdapter(RetailerAdapter):
    retailer_name = "Empty Retailer"

    def collect(self) -> Sequence[RetailerListing]:
        return ()


class TimeoutAdapter(RetailerAdapter):
    retailer_name = "Timed Out Retailer"

    def collect(self) -> Sequence[RetailerListing]:
        raise HttpFetchError(
            "Request failed after 3 attempts",
            url="https://retailer.example/product",
        )


class InvalidAdapter(RetailerAdapter):
    retailer_name = "Invalid Retailer"

    def collect(self) -> Sequence[RetailerListing]:
        return ("not a listing",)  # type: ignore[return-value]


def test_failed_adapter_does_not_discard_successful_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    result = CollectionService().collect((TimeoutAdapter(), SuccessfulAdapter()))

    assert len(result.listings) == 1
    assert result.successful_retailers == ("Working Retailer",)
    assert len(result.failures) == 1
    assert result.failures[0].retailer == "Timed Out Retailer"
    assert result.failures[0].error_type == "HttpFetchError"
    assert result.has_partial_failure is True
    assert "Retailer adapter collection failed" in caplog.text


def test_empty_adapter_is_a_success_not_a_failure() -> None:
    result = CollectionService().collect((EmptyAdapter(),))

    assert result.listings == ()
    assert result.successful_retailers == ("Empty Retailer",)
    assert result.failures == ()
    assert result.has_partial_failure is False


def test_invalid_adapter_contract_is_isolated() -> None:
    result = CollectionService().collect((InvalidAdapter(), SuccessfulAdapter()))

    assert len(result.listings) == 1
    assert result.successful_retailers == ("Working Retailer",)
    assert result.failures[0].retailer == "Invalid Retailer"
    assert result.failures[0].error_type == "TypeError"
