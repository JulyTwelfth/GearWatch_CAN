import logging
from collections.abc import Iterable
from dataclasses import dataclass

from app.adapters.base import RetailerAdapter
from app.schemas.retailer import RetailerListing

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AdapterFailure:
    retailer: str
    error_type: str
    resource: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    listings: tuple[RetailerListing, ...]
    successful_retailers: tuple[str, ...]
    failures: tuple[AdapterFailure, ...]

    @property
    def has_partial_failure(self) -> bool:
        return bool(self.failures) and bool(self.successful_retailers)


class CollectionService:
    """Run adapters independently so one retailer cannot stop the whole collection."""

    def collect(self, adapters: Iterable[RetailerAdapter]) -> CollectionResult:
        listings: list[RetailerListing] = []
        successful_retailers: list[str] = []
        failures: list[AdapterFailure] = []

        for adapter in adapters:
            retailer = adapter.retailer_name
            try:
                adapter_listings = tuple(adapter.collect())
                if not all(isinstance(item, RetailerListing) for item in adapter_listings):
                    raise TypeError("adapter returned a value outside the RetailerListing contract")
            except Exception as error:
                logger.exception(
                    "Retailer adapter collection failed",
                    extra={"retailer": retailer, "error_type": type(error).__name__},
                )
                failures.append(
                    AdapterFailure(retailer=retailer, error_type=type(error).__name__)
                )
                continue

            listings.extend(adapter_listings)
            item_failures = tuple(adapter.item_failures)
            failures.extend(
                AdapterFailure(
                    retailer=retailer,
                    error_type=failure.error_type,
                    resource=failure.resource,
                )
                for failure in item_failures
            )
            if adapter_listings or not item_failures:
                successful_retailers.append(retailer)
                logger.info(
                    "Retailer adapter collection succeeded",
                    extra={
                        "retailer": retailer,
                        "listing_count": len(adapter_listings),
                        "item_failure_count": len(item_failures),
                    },
                )

        return CollectionResult(
            listings=tuple(listings),
            successful_retailers=tuple(successful_retailers),
            failures=tuple(failures),
        )
