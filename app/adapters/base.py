from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.schemas.retailer import RetailerListing


class RetailerAdapter(ABC):
    """Stable boundary used by collection services, independent of retailer markup."""

    retailer_name: str

    @abstractmethod
    def collect(self) -> Sequence[RetailerListing]:
        """Return validated listings without writing to the database."""

