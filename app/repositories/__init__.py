"""Database access abstractions."""

from app.repositories.listings import (
    IngestResult,
    ingest_retailer_listing,
    record_fetch_status,
)

__all__ = ["IngestResult", "ingest_retailer_listing", "record_fetch_status"]
