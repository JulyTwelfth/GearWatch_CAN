import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db_session,
    get_product_detail_service,
    get_product_search_service,
)
from app.main import create_app
from app.schemas.product_detail import (
    CurrentProductOffer,
    InventoryHistoryPoint,
    PriceHistoryPoint,
    ProductDetailResponse,
    ProductHistoryParams,
    ProductHistoryResponse,
    ProductOfferHistory,
)
from app.schemas.search import (
    ProductOfferRead,
    ProductSearchParams,
    ProductSearchResponse,
)
from app.services.normalization import StockStatus, normalize_color, normalize_size
from app.services.product_detail import ProductNotFoundError

CHECKED_AT = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
RETAILER_URL = "https://retailer.example/products/fixture-alpine-shell"
SECOND_RETAILER_URL = "https://retailer.example/products/fixture-alpine-shell-monod"


def _search_offers() -> list[ProductOfferRead]:
    common = {
        "product_id": 1,
        "brand": "Arc'teryx",
        "product_name": "Fixture Alpine Shell",
        "model_number": "X000033333",
        "currency": "CAD",
        "model_name": "Fixture Alpine Shell",
        "style_number": "X000033333",
        "gender": "Men",
        "category": "Jackets",
        "source_status": "success",
        "status_checked_at": CHECKED_AT,
        "last_checked_at": CHECKED_AT,
    }
    return [
        ProductOfferRead(
            **common,
            retailer="Arc'teryx Canada",
            product_url=RETAILER_URL,
            current_price=Decimal("300.00"),
            original_price=Decimal("400.00"),
            discount_percentage=Decimal("25.00"),
            color="Black Sapphire",
            size="M",
            stock_status=StockStatus.AVAILABLE,
        ),
        ProductOfferRead(
            **common,
            retailer="Monod Sports",
            product_url=SECOND_RETAILER_URL,
            current_price=Decimal("280.00"),
            original_price=Decimal("400.00"),
            discount_percentage=Decimal("30.00"),
            color="Black Sapphire",
            size="M",
            stock_status=StockStatus.AVAILABLE,
        ),
        ProductOfferRead(
            **common,
            retailer="Arc'teryx Outlet Canada",
            product_url=RETAILER_URL,
            current_price=Decimal("400.00"),
            original_price=None,
            discount_percentage=Decimal("0.00"),
            color="Solitude",
            size="L",
            stock_status=StockStatus.OUT_OF_STOCK,
        ),
    ]


class E2ESearchService:
    def search(
        self,
        _session: Session,
        params: ProductSearchParams,
    ) -> ProductSearchResponse:
        if params.q and params.q.casefold() == "system-error":
            raise SQLAlchemyError("synthetic E2E database failure")

        offers = _search_offers()
        if params.q:
            query = params.q.casefold()
            offers = [
                offer
                for offer in offers
                if query in offer.product_name.casefold()
                or query in (offer.model_number or "").casefold()
            ]
        if params.model:
            offers = [
                offer
                for offer in offers
                if (offer.model_number or "").casefold() == params.model.casefold()
            ]
        if params.size:
            expected_size = normalize_size(params.size)
            offers = [offer for offer in offers if offer.size == expected_size]
        if params.color:
            expected_color = normalize_color(params.color)
            offers = [offer for offer in offers if offer.color == expected_color]
        if params.min_discount:
            offers = [
                offer
                for offer in offers
                if offer.discount_percentage >= params.min_discount
            ]
        if params.stock_status:
            offers = [
                offer for offer in offers if offer.stock_status is params.stock_status
            ]
        if params.category:
            offers = [offer for offer in offers if offer.category == params.category]
        if params.gender:
            offers = [offer for offer in offers if offer.gender == params.gender.value]
        if params.retailer:
            offers = [offer for offer in offers if offer.retailer == params.retailer]
        if params.sort == "price_asc":
            offers.sort(key=lambda offer: offer.current_price)
        elif params.sort == "discount_desc":
            offers.sort(key=lambda offer: offer.discount_percentage, reverse=True)
        return ProductSearchResponse(
            items=offers,
            total=len(offers),
            limit=params.limit,
            offset=params.offset,
        )


class E2EDetailService:
    def get_detail(self, _session: Session, product_id: int) -> ProductDetailResponse:
        if product_id != 1:
            raise ProductNotFoundError(product_id)
        offers = _search_offers()
        return ProductDetailResponse(
            product_id=1,
            brand="Arc'teryx",
            product_name="Fixture Alpine Shell",
            model_number="X000033333",
            last_checked_at=CHECKED_AT,
            offers=[
                CurrentProductOffer(
                    listing_id=index + 10,
                    variant_id=index + 20,
                    retailer=offer.retailer,
                    current_price=offer.current_price,
                    original_price=offer.original_price,
                    discount_percentage=offer.discount_percentage,
                    currency=offer.currency,
                    color=offer.color,
                    size=offer.size,
                    stock_status=offer.stock_status,
                    product_url=offer.product_url,
                    source_status=offer.source_status,
                    status_checked_at=offer.status_checked_at,
                    last_checked_at=offer.last_checked_at,
                )
                for index, offer in enumerate(offers)
            ],
        )

    def get_history(
        self,
        _session: Session,
        product_id: int,
        params: ProductHistoryParams,
    ) -> ProductHistoryResponse:
        if product_id != 1:
            raise ProductNotFoundError(product_id)
        return ProductHistoryResponse(
            product_id=1,
            brand="Arc'teryx",
            product_name="Fixture Alpine Shell",
            model_number="X000033333",
            limit_per_offer=params.limit_per_offer,
            offers=[
                ProductOfferHistory(
                    listing_id=10,
                    variant_id=20,
                    retailer="Fixture Outdoor Canada",
                    color="Black Sapphire",
                    size="M",
                    product_url=RETAILER_URL,
                    last_checked_at=CHECKED_AT,
                    price_history=[
                        PriceHistoryPoint(
                            current_price=Decimal("350.00"),
                            original_price=Decimal("400.00"),
                            discount_percentage=Decimal("12.50"),
                            currency="CAD",
                            checked_at=CHECKED_AT - timedelta(days=7),
                        ),
                        PriceHistoryPoint(
                            current_price=Decimal("300.00"),
                            original_price=Decimal("400.00"),
                            discount_percentage=Decimal("25.00"),
                            currency="CAD",
                            checked_at=CHECKED_AT,
                        ),
                    ],
                    inventory_history=[
                        InventoryHistoryPoint(
                            stock_status=StockStatus.UNKNOWN,
                            checked_at=CHECKED_AT - timedelta(days=7),
                        ),
                        InventoryHistoryPoint(
                            stock_status=StockStatus.AVAILABLE,
                            checked_at=CHECKED_AT,
                        ),
                    ],
                ),
                ProductOfferHistory(
                    listing_id=11,
                    variant_id=21,
                    retailer="Fixture Outdoor Canada",
                    color="Solitude",
                    size="L",
                    product_url=RETAILER_URL,
                    last_checked_at=CHECKED_AT,
                    price_history=[
                        PriceHistoryPoint(
                            current_price=Decimal("400.00"),
                            original_price=None,
                            discount_percentage=Decimal("0.00"),
                            currency="CAD",
                            checked_at=CHECKED_AT,
                        )
                    ],
                    inventory_history=[
                        InventoryHistoryPoint(
                            stock_status=StockStatus.OUT_OF_STOCK,
                            checked_at=CHECKED_AT,
                        )
                    ],
                ),
            ],
        )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return int(server_socket.getsockname()[1])


@pytest.fixture(scope="session")
def live_server_url() -> Iterator[str]:
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: object()
    application.dependency_overrides[get_product_search_service] = E2ESearchService
    application.dependency_overrides[get_product_detail_service] = E2EDetailService

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=0.5) as response:
                if response.status == 200:
                    break
        except (OSError, urllib.error.URLError):
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("The local E2E server did not start within 10 seconds")

    yield base_url
    server.should_exit = True
    thread.join(timeout=5)
    if thread.is_alive():
        pytest.fail("The local E2E server did not stop cleanly")


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.route(
        "https://retailer.example/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                "<html><title>Fixture Retailer</title>"
                "<h1>Fixture retailer destination</h1></html>"
            ),
        ),
    )
    page = context.new_page()
    yield page
    context.close()
