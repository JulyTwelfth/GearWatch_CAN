"""Database access abstractions."""

from app.repositories.listings import (
    IngestResult,
    deactivate_missing_listing_variants,
    ingest_retailer_listing,
    record_fetch_status,
)

__all__ = [
    "IngestResult",
    "deactivate_missing_listing_variants",
    "ingest_retailer_listing",
    "record_fetch_status",
]
