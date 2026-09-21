from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Listing,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.schemas.search import ProductOfferRead, ProductSearchParams, ProductSearchResponse
from app.services.normalization import (
    normalize_color,
    normalize_lookup_key,
    normalize_model_number,
    normalize_size,
)


class ProductSearchService:
    """Query the latest price and inventory state for each retailer variant."""

    def search(
        self,
        session: Session,
        params: ProductSearchParams,
    ) -> ProductSearchResponse:
        latest_price = self._latest_price_subquery()
        latest_inventory = self._latest_inventory_subquery()

        statement = (
            select(
                Product.id.label("product_id"),
                Product.brand,
                Product.name.label("product_name"),
                Product.model_number,
                Product.model_name,
                Product.style_number,
                Product.gender,
                Product.category,
                Product.image_url,
                Retailer.name.label("retailer"),
                latest_price.c.current_price,
                latest_price.c.original_price,
                latest_price.c.discount_percentage,
                latest_price.c.currency,
                ProductVariant.color,
                ProductVariant.size,
                latest_inventory.c.stock_status,
                Listing.product_url,
                Listing.source_status,
                Listing.status_checked_at,
                Listing.last_checked_at,
            )
            .select_from(Product)
            .join(Listing, Listing.product_id == Product.id)
            .join(Retailer, Retailer.id == Listing.retailer_id)
            .join(
                latest_price,
                and_(
                    latest_price.c.listing_id == Listing.id,
                    latest_price.c.snapshot_rank == 1,
                ),
            )
            .join(ProductVariant, ProductVariant.id == latest_price.c.variant_id)
            .join(
                latest_inventory,
                and_(
                    latest_inventory.c.listing_id == Listing.id,
                    latest_inventory.c.variant_id == ProductVariant.id,
                    latest_inventory.c.snapshot_rank == 1,
                ),
            )
            .where(Product.brand == "Arc'teryx", Retailer.is_active.is_(True))
        )
        statement = self._apply_filters(
            statement, params, latest_price, latest_inventory
        )

        count_statement = select(func.count()).select_from(
            statement.order_by(None).subquery()
        )
        total = session.scalar(count_statement) or 0

        rows = session.execute(
            statement.order_by(*self._sort_columns(params, latest_price))
            .limit(params.limit)
            .offset(params.offset)
        ).mappings()

        return ProductSearchResponse(
            items=[ProductOfferRead.model_validate(row) for row in rows],
            total=total,
            limit=params.limit,
            offset=params.offset,
        )

    @staticmethod
    def _latest_price_subquery() -> Any:
        return select(
            PriceSnapshot.listing_id,
            PriceSnapshot.variant_id,
            PriceSnapshot.current_price,
            PriceSnapshot.original_price,
            PriceSnapshot.discount_percentage,
            PriceSnapshot.currency,
            func.row_number()
            .over(
                partition_by=(PriceSnapshot.listing_id, PriceSnapshot.variant_id),
                order_by=(PriceSnapshot.checked_at.desc(), PriceSnapshot.id.desc()),
            )
            .label("snapshot_rank"),
        ).subquery("latest_price")

    @staticmethod
    def _latest_inventory_subquery() -> Any:
        return select(
            InventorySnapshot.listing_id,
            InventorySnapshot.variant_id,
            InventorySnapshot.stock_status,
            func.row_number()
            .over(
                partition_by=(
                    InventorySnapshot.listing_id,
                    InventorySnapshot.variant_id,
                ),
                order_by=(
                    InventorySnapshot.checked_at.desc(),
                    InventorySnapshot.id.desc(),
                ),
            )
            .label("snapshot_rank"),
        ).subquery("latest_inventory")

    @staticmethod
    def _apply_filters(
        statement: Select[Any],
        params: ProductSearchParams,
        latest_price: Any,
        latest_inventory: Any,
    ) -> Select[Any]:
        if params.q:
            search_key = normalize_lookup_key(params.q)
            statement = statement.where(
                or_(
                    Product.normalized_name.contains(search_key),
                    Product.normalized_model_number.contains(search_key),
                    Product.normalized_model_name.contains(search_key),
                    Product.normalized_style_number.contains(search_key),
                )
            )
        if params.model:
            model_key = normalize_model_number(params.model)
            lookup_key = normalize_lookup_key(params.model)
            statement = statement.where(
                or_(
                    Product.normalized_model_number == model_key.casefold(),
                    Product.normalized_style_number == model_key.casefold(),
                    Product.normalized_model_name == lookup_key,
                )
            )
        if params.size:
            size_key = normalize_lookup_key(normalize_size(params.size))
            statement = statement.where(ProductVariant.normalized_size == size_key)
        if params.color:
            color_key = normalize_lookup_key(normalize_color(params.color))
            statement = statement.where(ProductVariant.normalized_color == color_key)
        if params.min_discount > 0:
            statement = statement.where(
                latest_price.c.discount_percentage >= params.min_discount
            )
        if params.stock_status:
            statement = statement.where(
                latest_inventory.c.stock_status == params.stock_status
            )
        if params.category:
            statement = statement.where(
                func.lower(Product.category) == params.category.casefold()
            )
        if params.gender:
            statement = statement.where(Product.gender == params.gender.value)
        if params.retailer:
            statement = statement.where(
                Retailer.slug == normalize_lookup_key(params.retailer)
            )
        return statement

    @staticmethod
    def _sort_columns(params: ProductSearchParams, latest_price: Any) -> tuple[Any, ...]:
        tie_breakers = (
            Product.name,
            Retailer.name,
            ProductVariant.color,
            ProductVariant.size,
        )
        if params.sort == "price_asc":
            return (latest_price.c.current_price, *tie_breakers)
        if params.sort == "discount_desc":
            return (
                latest_price.c.discount_percentage.desc(),
                latest_price.c.current_price,
                *tie_breakers,
            )
        return (Product.name, latest_price.c.current_price, *tie_breakers[1:])
