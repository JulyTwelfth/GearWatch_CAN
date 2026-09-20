from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.retailer import RetailerListing


@dataclass(frozen=True, slots=True)
class AdapterItemFailure:
    """Sanitized failure metadata for one configured adapter resource."""

    error_type: str
    resource: str


class RetailerAdapter(ABC):
    """Stable boundary used by collection services, independent of retailer markup."""

    retailer_name: str

    @property
    def item_failures(self) -> Sequence[AdapterItemFailure]:
        """Return per-resource failures from the most recent collection cycle."""
        return ()

    @abstractmethod
    def collect(self) -> Sequence[RetailerListing]:
        """Return validated listings without writing to the database."""
