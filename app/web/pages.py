import logging
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db_session,
    get_product_detail_service,
    get_product_search_service,
)
from app.schemas.product_detail import ProductHistoryParams
from app.schemas.search import ProductSearchParams
from app.services.product_detail import ProductDetailService, ProductNotFoundError
from app.services.product_search import ProductSearchService

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _error_page(
    request: Request,
    *,
    status_code: int,
    title: str,
    message: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "status_code": status_code,
            "title": title,
            "message": message,
            "page_last_checked": None,
        },
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse)
def search_page(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductSearchService, Depends(get_product_search_service)],
    q: Annotated[str | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    size: Annotated[str | None, Query()] = None,
    color: Annotated[str | None, Query()] = None,
    min_discount: Annotated[str, Query()] = "0",
    stock_status: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    filters = {
        "q": q or "",
        "model": model or "",
        "size": size or "",
        "color": color or "",
        "min_discount": min_discount,
        "stock_status": stock_status or "",
    }
    try:
        params = ProductSearchParams(
            q=_optional_text(q),
            model=_optional_text(model),
            size=_optional_text(size),
            color=_optional_text(color),
            min_discount=_optional_text(min_discount) or Decimal("0"),
            stock_status=_optional_text(stock_status),
            limit=100,
        )
    except (ValidationError, ValueError):
        return _error_page(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Invalid search filters",
            message="Review the filters and try the search again.",
        )

    try:
        results = service.search(session, params)
    except SQLAlchemyError as error:
        logger.error(
            "Search page database query failed",
            extra={"error_type": type(error).__name__},
        )
        return _error_page(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Search temporarily unavailable",
            message="Saved product data could not be loaded. Please try again later.",
        )

    page_last_checked = max(
        (offer.last_checked_at for offer in results.items),
        default=None,
    )
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "results": results,
            "filters": filters,
            "page_last_checked": page_last_checked,
        },
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail_page(
    request: Request,
    product_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductDetailService, Depends(get_product_detail_service)],
) -> HTMLResponse:
    if not product_id.isdigit() or int(product_id) < 1:
        return _error_page(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Product not found",
            message="This product may not have been collected yet.",
        )
    parsed_product_id = int(product_id)
    try:
        product = service.get_detail(session, parsed_product_id)
        history = service.get_history(
            session,
            parsed_product_id,
            ProductHistoryParams(limit_per_offer=50),
        )
    except ProductNotFoundError:
        return _error_page(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Product not found",
            message="This product may not have been collected yet.",
        )
    except SQLAlchemyError as error:
        logger.error(
            "Product page database query failed",
            extra={"error_type": type(error).__name__},
        )
        return _error_page(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Product temporarily unavailable",
            message="Saved product details could not be loaded. Please try again later.",
        )

    return templates.TemplateResponse(
        request=request,
        name="product_detail.html",
        context={
            "product": product,
            "history": history,
            "page_last_checked": product.last_checked_at,
        },
    )
