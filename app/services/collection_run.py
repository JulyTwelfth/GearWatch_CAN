from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.base import RetailerAdapter
from app.repositories import IngestResult, ingest_retailer_listing
from app.schemas.retailer import RetailerListing
from app.services.collection import AdapterFailure, CollectionService

ListingWriter = Callable[[Session, RetailerListing], IngestResult]


@dataclass(frozen=True, slots=True)
class CollectionRunSummary:
    configured_retailers: tuple[str, ...]
    successful_retailers: tuple[str, ...]
    failures: tuple[AdapterFailure, ...]
    listings_processed: int
    price_snapshots_created: int
    inventory_snapshots_created: int

    @property
    def status(self) -> str:
        if self.failures and self.successful_retailers:
            return "partial_failure"
        if self.failures:
            return "failed"
        return "completed"


class CollectionRunService:
    """Collect retailer rows and persist successful results inside the caller's transaction."""

    def __init__(
        self,
        *,
        collection_service: CollectionService | None = None,
        listing_writer: ListingWriter = ingest_retailer_listing,
    ) -> None:
        self._collection_service = collection_service or CollectionService()
        self._listing_writer = listing_writer

    def run(
        self,
        adapters: Iterable[RetailerAdapter],
        session: Session,
    ) -> CollectionRunSummary:
        configured_adapters = tuple(adapters)
        collected = self._collection_service.collect(configured_adapters)
        price_snapshots_created = 0
        inventory_snapshots_created = 0

        for listing in collected.listings:
            result = self._listing_writer(session, listing)
            price_snapshots_created += int(result.price_snapshot_created)
            inventory_snapshots_created += int(result.inventory_snapshot_created)

        return CollectionRunSummary(
            configured_retailers=tuple(
                adapter.retailer_name for adapter in configured_adapters
            ),
            successful_retailers=collected.successful_retailers,
            failures=collected.failures,
            listings_processed=len(collected.listings),
            price_snapshots_created=price_snapshots_created,
            inventory_snapshots_created=inventory_snapshots_created,
        )
