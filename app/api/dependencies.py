from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from app.db import create_db_engine, create_session_factory
from app.services.product_detail import ProductDetailService
from app.services.product_search import ProductSearchService


@lru_cache
def get_api_session_factory() -> sessionmaker[Session]:
    return create_session_factory(create_db_engine())


def get_db_session() -> Iterator[Session]:
    with get_api_session_factory()() as session:
        yield session


def get_product_search_service() -> ProductSearchService:
    return ProductSearchService()


def get_product_detail_service() -> ProductDetailService:
    return ProductDetailService()
