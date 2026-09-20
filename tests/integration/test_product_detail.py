from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.repositories import ingest_retailer_listing
from app.schemas.product_detail import ProductHistoryParams
from app.services.normalization import StockStatus
from app.services.product_detail import ProductDetailService, ProductNotFoundError
from tests.integration.test_product_search import BASE_TIME, listing, seed_search_data

pytestmark = pytest.mark.integration


def product_id(session: Session) -> int:
    return session.scalar(
        select(Product.id).where(Product.normalized_model_number == "x000066666")
    )


def add_inventory_change(session: Session) -> None:
    ingest_retailer_listing(
        session,
        listing(
            retailer="Alpha Outdoors",
            url_slug="alpha-shell",
            color="Black Sapphire",
            size="M",
            current_price="250.00",
            original_price="400.00",
            stock_status="Out of Stock",
            checked_at=BASE_TIME + timedelta(hours=2),
        ),
    )


def test_detail_returns_latest_offer_state_and_product_last_checked(
    db_session: Session,
) -> None:
    seed_search_data(db_session)
    add_inventory_change(db_session)

    result = ProductDetailService().get_detail(db_session, product_id(db_session))

    assert len(result.offers) == 3
    assert result.last_checked_at == BASE_TIME + timedelta(hours=2)
    alpha_medium = next(
        offer
        for offer in result.offers
        if offer.retailer == "Alpha Outdoors" and offer.size == "M"
    )
    assert alpha_medium.current_price == Decimal("250.00")
    assert alpha_medium.stock_status is StockStatus.OUT_OF_STOCK


def test_history_returns_change_only_points_in_chronological_order(
    db_session: Session,
) -> None:
    seed_search_data(db_session)
    add_inventory_change(db_session)
    service = ProductDetailService()
    detail = service.get_detail(db_session, product_id(db_session))
    alpha_medium = next(
        offer
        for offer in detail.offers
        if offer.retailer == "Alpha Outdoors" and offer.size == "M"
    )

    result = service.get_history(
        db_session,
        detail.product_id,
        ProductHistoryParams(
            listing_id=alpha_medium.listing_id,
            variant_id=alpha_medium.variant_id,
            limit_per_offer=10,
        ),
    )

    assert len(result.offers) == 1
    history = result.offers[0]
    assert [point.current_price for point in history.price_history] == [
        Decimal("300.00"),
        Decimal("250.00"),
    ]
    assert [point.stock_status for point in history.inventory_history] == [
        StockStatus.AVAILABLE,
        StockStatus.OUT_OF_STOCK,
    ]
    assert [point.checked_at for point in history.price_history] == sorted(
        point.checked_at for point in history.price_history
    )


def test_history_limit_keeps_most_recent_point_per_offer(db_session: Session) -> None:
    seed_search_data(db_session)
    add_inventory_change(db_session)
    service = ProductDetailService()
    product = product_id(db_session)

    result = service.get_history(
        db_session,
        product,
        ProductHistoryParams(limit_per_offer=1),
    )

    alpha_medium = next(
        offer
        for offer in result.offers
        if offer.retailer == "Alpha Outdoors" and offer.size == "M"
    )
    assert [point.current_price for point in alpha_medium.price_history] == [
        Decimal("250.00")
    ]
    assert [point.stock_status for point in alpha_medium.inventory_history] == [
        StockStatus.OUT_OF_STOCK
    ]


def test_missing_product_raises_domain_error(db_session: Session) -> None:
    with pytest.raises(ProductNotFoundError):
        ProductDetailService().get_detail(db_session, 999_999)
