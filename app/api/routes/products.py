import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db_session,
    get_product_detail_service,
    get_product_search_service,
)
from app.schemas.product_detail import (
    ProductDetailResponse,
    ProductHistoryParams,
    ProductHistoryResponse,
)
from app.schemas.search import ProductSearchParams, ProductSearchResponse
from app.services.product_detail import ProductDetailService, ProductNotFoundError
from app.services.product_search import ProductSearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductSearchResponse)
def search_products(
    params: Annotated[ProductSearchParams, Query()],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductSearchService, Depends(get_product_search_service)],
) -> ProductSearchResponse:
    try:
        return service.search(session, params)
    except SQLAlchemyError as error:
        logger.error(
            "Product search database query failed",
            extra={"error_type": type(error).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "Product search is temporarily unavailable.",
            },
        ) from error


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product_detail(
    product_id: Annotated[int, Path(gt=0)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductDetailService, Depends(get_product_detail_service)],
) -> ProductDetailResponse:
    try:
        return service.get_detail(session, product_id)
    except ProductNotFoundError as error:
        raise _product_not_found(error) from error
    except SQLAlchemyError as error:
        raise _database_unavailable("Product detail", error) from error


@router.get("/{product_id}/history", response_model=ProductHistoryResponse)
def get_product_history(
    product_id: Annotated[int, Path(gt=0)],
    params: Annotated[ProductHistoryParams, Query()],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductDetailService, Depends(get_product_detail_service)],
) -> ProductHistoryResponse:
    try:
        return service.get_history(session, product_id, params)
    except ProductNotFoundError as error:
        raise _product_not_found(error) from error
    except SQLAlchemyError as error:
        raise _database_unavailable("Product history", error) from error


def _product_not_found(_error: ProductNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "product_not_found", "message": "Product was not found."},
    )


def _database_unavailable(operation: str, error: SQLAlchemyError) -> HTTPException:
    logger.error(
        "%s database query failed",
        operation,
        extra={"error_type": type(error).__name__},
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "database_unavailable",
            "message": "Product data is temporarily unavailable.",
        },
    )
