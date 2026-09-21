import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.adapters.errors import AdapterParseError
from app.core.http import HttpFetchError, PoliteHttpClient
from app.schemas.retailer import RetailerListing
from app.services.normalization import SourceStatus, normalize_lookup_key

logger = logging.getLogger(__name__)


class HtmlClient(Protocol):
    def get_html(self, url: str) -> str: ...

    def get_json(self, url: str) -> str: ...

    def get_xml(self, url: str) -> str: ...


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


@dataclass(frozen=True, slots=True)
class CatalogRequest:
    """One bounded public catalogue page used to discover product URLs."""

    url: str
    content_type: Literal["html", "json", "xml"] = "html"


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
        product_urls, initial_failures, initial_statuses = self._collection_plan()
        failures = list(initial_failures)
        statuses = list(initial_statuses)
        for product_url in product_urls:
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

    def _collection_plan(
        self,
    ) -> tuple[
        Sequence[str], Sequence[AdapterItemFailure], Sequence[AdapterFetchStatus]
    ]:
        return self._product_urls, (), ()

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


class CatalogDiscoveryAdapter(ConfiguredUrlAdapter, ABC):
    """Add bounded, failure-isolated catalogue discovery to a product adapter."""

    def __init__(
        self,
        product_urls: Sequence[str] = (),
        *,
        discovery_enabled: bool = False,
        discovery_max_products: int = 15,
        discovery_max_pages: int = 3,
        http_client: HtmlClient | None = None,
        checked_at_factory: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            product_urls,
            http_client=http_client,
            checked_at_factory=checked_at_factory,
        )
        if not 1 <= discovery_max_products <= 50:
            raise ValueError("discovery_max_products must be between 1 and 50")
        if not 1 <= discovery_max_pages <= 10:
            raise ValueError("discovery_max_pages must be between 1 and 10")
        self._discovery_enabled = discovery_enabled
        self._discovery_max_products = discovery_max_products
        self._discovery_max_pages = discovery_max_pages
        self._last_discovered_urls: tuple[str, ...] = ()

    @property
    def discovered_product_urls(self) -> Sequence[str]:
        return self._last_discovered_urls

    @abstractmethod
    def catalog_requests(self) -> Sequence[CatalogRequest]:
        """Return a small, deterministic set of public catalogue pages."""

    @abstractmethod
    def parse_catalog_page(self, content: str, *, source_url: str) -> Sequence[str]:
        """Return validated retailer product URLs from one saved catalogue page."""

    def prioritize_discovered_urls(self, urls: Sequence[str]) -> Sequence[str]:
        return urls

    def discovery_identity(self, product_url: str) -> str:
        return product_url.casefold()

    def _collection_plan(
        self,
    ) -> tuple[
        Sequence[str], Sequence[AdapterItemFailure], Sequence[AdapterFetchStatus]
    ]:
        if not self._discovery_enabled:
            return super()._collection_plan()

        failures: list[AdapterItemFailure] = []
        statuses: list[AdapterFetchStatus] = []
        discovered: list[str] = []
        for request in tuple(self.catalog_requests())[: self._discovery_max_pages]:
            checked_at = self._checked_at_factory()
            try:
                content = self._fetch_catalog(request)
                page_urls = self.parse_catalog_page(content, source_url=request.url)
                if not page_urls:
                    raise AdapterParseError("catalogue page contains no product URLs")
                discovered.extend(page_urls)
                statuses.append(
                    AdapterFetchStatus(
                        resource=request.url,
                        status=SourceStatus.SUCCESS,
                        checked_at=checked_at,
                    )
                )
            except (AdapterParseError, HttpFetchError) as error:
                status = self._failure_status(error)
                failures.append(
                    AdapterItemFailure(
                        error_type=type(error).__name__,
                        resource=request.url,
                        status=status,
                    )
                )
                statuses.append(
                    AdapterFetchStatus(
                        resource=request.url,
                        status=status,
                        checked_at=checked_at,
                        error_type=type(error).__name__,
                    )
                )
                logger.warning(
                    "Retailer catalogue discovery failed",
                    extra={
                        "retailer": self.retailer_name,
                        "catalogue_url": request.url,
                        "source_status": status.value,
                        "error_type": type(error).__name__,
                    },
                )

        prioritized = self.prioritize_discovered_urls(
            tuple(dict.fromkeys(discovered))
        )
        selected: list[str] = []
        identities: set[str] = set()
        for product_url in prioritized:
            identity = self.discovery_identity(product_url)
            if identity in identities:
                continue
            identities.add(identity)
            selected.append(product_url)
        self._last_discovered_urls = tuple(selected)

        configured = list(self._product_urls)
        seen = set(configured)
        remaining = max(0, self._discovery_max_products - len(configured))
        for product_url in selected:
            if remaining == 0:
                break
            if product_url in seen:
                continue
            configured.append(product_url)
            seen.add(product_url)
            remaining -= 1
        return tuple(configured), tuple(failures), tuple(statuses)

    def _fetch_catalog(self, request: CatalogRequest) -> str:
        if request.content_type == "json":
            return self._http_client.get_json(request.url)
        if request.content_type == "xml":
            return self._http_client.get_xml(request.url)
        return self._http_client.get_html(request.url)
