"""Database access abstractions."""

from app.repositories.listings import IngestResult, ingest_retailer_listing

__all__ = ["IngestResult", "ingest_retailer_listing"]
