import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.adapters.errors import AdapterParseError
from app.core.http import HttpFetchError, PoliteHttpClient
from app.schemas.retailer import RetailerListing
from app.services.normalization import SourceStatus, normalize_lookup_key

logger = logging.getLogger(__name__)


class HtmlClient(Protocol):
    def get_html(self, url: str) -> str: ...


@dataclass(frozen=True, slots=True)
class AdapterItemFailure:
    """Sanitized failure metadata for one configured adapter resource."""

    error_type: str
    resource: str
    status: SourceStatus = SourceStatus.UNAVAILABLE


@dataclass(frozen=True, slots=True)
class AdapterFetchStatus:
    resource: str
    status: SourceStatus
    checked_at: datetime
    error_type: str | None = None


class RetailerAdapter(ABC):
    """Stable boundary used by collection services, independent of retailer markup."""

    retailer_name: str

    @property
    def item_failures(self) -> Sequence[AdapterItemFailure]:
        return ()

    @property
    def fetch_statuses(self) -> Sequence[AdapterFetchStatus]:
        return ()

    @abstractmethod
    def collect(self) -> Sequence[RetailerListing]:
        """Return validated listings without writing to the database."""


class ConfiguredUrlAdapter(RetailerAdapter, ABC):
    """Shared bounded workflow for adapters using explicitly configured product URLs."""

    def __init__(
        self,
        product_urls: Sequence[str] = (),
        *,
        http_client: HtmlClient | None = None,
        checked_at_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._product_urls = tuple(self._validate_product_url(url) for url in product_urls)
        self._http_client = http_client or PoliteHttpClient()
        self._checked_at_factory = checked_at_factory or (lambda: datetime.now(UTC))
        self._item_failures: tuple[AdapterItemFailure, ...] = ()
        self._fetch_statuses: tuple[AdapterFetchStatus, ...] = ()

    @property
    def item_failures(self) -> Sequence[AdapterItemFailure]:
        return self._item_failures

    @property
    def fetch_statuses(self) -> Sequence[AdapterFetchStatus]:
        return self._fetch_statuses

    def search_products(self, query: str) -> Sequence[str]:
        """Search the configured catalogue without crawling retailer search pages."""
        key = normalize_lookup_key(query)
        return tuple(url for url in self._product_urls if key in normalize_lookup_key(url))

    def fetch_product(
        self, product_url: str, *, checked_at: datetime | None = None
    ) -> Sequence[RetailerListing]:
        safe_url = self._validate_product_url(product_url)
        html = self._http_client.get_html(safe_url)
        return self.parse_product_page(
            html,
            product_url=safe_url,
            checked_at=checked_at or self._checked_at_factory(),
        )

    @staticmethod
    def fetch_inventory(product: Sequence[RetailerListing]) -> Sequence[RetailerListing]:
        """Inventory is already represented at variant level in the shared contract."""
        return product

    def collect(self) -> Sequence[RetailerListing]:
        listings: list[RetailerListing] = []
        failures: list[AdapterItemFailure] = []
        statuses: list[AdapterFetchStatus] = []
        for product_url in self._product_urls:
            checked_at = self._checked_at_factory()
            try:
                product = self.fetch_product(product_url, checked_at=checked_at)
                listings.extend(self.fetch_inventory(product))
                statuses.append(
                    AdapterFetchStatus(
                        resource=product_url,
                        status=SourceStatus.SUCCESS,
                        checked_at=checked_at,
                    )
                )
            except (AdapterParseError, HttpFetchError) as error:
                status = self._failure_status(error)
                failure = AdapterItemFailure(
                    error_type=type(error).__name__,
                    resource=product_url,
                    status=status,
                )
                failures.append(failure)
                statuses.append(
                    AdapterFetchStatus(
                        resource=product_url,
                        status=status,
                        checked_at=checked_at,
                        error_type=type(error).__name__,
                    )
                )
                logger.warning(
                    "Retailer product collection failed",
                    extra={
                        "retailer": self.retailer_name,
                        "product_url": product_url,
                        "source_status": status.value,
                        "error_type": type(error).__name__,
                    },
                )
        self._item_failures = tuple(failures)
        self._fetch_statuses = tuple(statuses)
        return listings

    @staticmethod
    def _failure_status(error: AdapterParseError | HttpFetchError) -> SourceStatus:
        if isinstance(error, AdapterParseError):
            return SourceStatus.PARSE_ERROR
        if error.status_code in {401, 403}:
            return SourceStatus.BLOCKED
        return SourceStatus.UNAVAILABLE

    @classmethod
    @abstractmethod
    def _validate_product_url(cls, url: str) -> str:
        """Validate and return a safe canonical product URL."""

    @abstractmethod
    def parse_product_page(
        self,
        html: str,
        *,
        product_url: str,
        checked_at: datetime,
    ) -> Sequence[RetailerListing]:
        """Parse a saved or fetched product page into variant rows."""
