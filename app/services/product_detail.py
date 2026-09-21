from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Listing,
    ListingVariant,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.schemas.product_detail import (
    CurrentProductOffer,
    InventoryHistoryPoint,
    PriceHistoryPoint,
    ProductDetailResponse,
    ProductHistoryParams,
    ProductHistoryResponse,
    ProductOfferHistory,
)


class ProductNotFoundError(LookupError):
    """Raised when a requested canonical product does not exist."""


class ProductDetailService:
    """Read current offers and persisted change history for one product."""

    def get_detail(self, session: Session, product_id: int) -> ProductDetailResponse:
        product = self._get_product(session, product_id)
        latest_price = self._latest_price_subquery()
        latest_inventory = self._latest_inventory_subquery()

        rows = session.execute(
            select(
                Listing.id.label("listing_id"),
                ProductVariant.id.label("variant_id"),
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
            .select_from(Listing)
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
                ListingVariant,
                and_(
                    ListingVariant.listing_id == Listing.id,
                    ListingVariant.variant_id == ProductVariant.id,
                    ListingVariant.is_active.is_(True),
                ),
            )
            .join(
                latest_inventory,
                and_(
                    latest_inventory.c.listing_id == Listing.id,
                    latest_inventory.c.variant_id == ProductVariant.id,
                    latest_inventory.c.snapshot_rank == 1,
                ),
            )
            .where(Listing.product_id == product_id, Retailer.is_active.is_(True))
            .order_by(
                latest_price.c.current_price,
                Retailer.name,
                ProductVariant.color,
                ProductVariant.size,
            )
        ).mappings()
        offers = [CurrentProductOffer.model_validate(row) for row in rows]

        return ProductDetailResponse(
            **product,
            last_checked_at=max(
                (offer.last_checked_at for offer in offers),
                default=None,
            ),
            offers=offers,
        )

    def get_history(
        self,
        session: Session,
        product_id: int,
        params: ProductHistoryParams,
    ) -> ProductHistoryResponse:
        product = self._get_product(session, product_id)
        offers = self._history_offers(session, product_id, params)
        if not offers:
            return ProductHistoryResponse(
                **product,
                limit_per_offer=params.limit_per_offer,
                offers=[],
            )

        offer_by_key = {
            (offer.listing_id, offer.variant_id): offer for offer in offers
        }
        for row in self._price_history(session, product_id, params):
            offer_by_key[(row["listing_id"], row["variant_id"])].price_history.append(
                PriceHistoryPoint(
                    current_price=row["current_price"],
                    original_price=row["original_price"],
                    discount_percentage=row["discount_percentage"],
                    currency=row["currency"],
                    checked_at=row["checked_at"],
                )
            )
        for row in self._inventory_history(session, product_id, params):
            offer_by_key[(row["listing_id"], row["variant_id"])].inventory_history.append(
                InventoryHistoryPoint(
                    stock_status=row["stock_status"],
                    checked_at=row["checked_at"],
                )
            )

        return ProductHistoryResponse(
            **product,
            limit_per_offer=params.limit_per_offer,
            offers=offers,
        )

    @staticmethod
    def _get_product(session: Session, product_id: int) -> dict[str, Any]:
        product = session.execute(
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
            ).where(Product.id == product_id)
        ).mappings().one_or_none()
        if product is None:
            raise ProductNotFoundError(product_id)
        return dict(product)

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
        ).subquery("detail_latest_price")

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
        ).subquery("detail_latest_inventory")

    @staticmethod
    def _history_filters(
        product_id: int,
        params: ProductHistoryParams,
    ) -> list[Any]:
        filters = [Listing.product_id == product_id, Retailer.is_active.is_(True)]
        if params.listing_id is not None:
            filters.append(Listing.id == params.listing_id)
        if params.variant_id is not None:
            filters.append(ProductVariant.id == params.variant_id)
        return filters

    def _history_offers(
        self,
        session: Session,
        product_id: int,
        params: ProductHistoryParams,
    ) -> list[ProductOfferHistory]:
        rows = session.execute(
            select(
                Listing.id.label("listing_id"),
                ProductVariant.id.label("variant_id"),
                Retailer.name.label("retailer"),
                ProductVariant.color,
                ProductVariant.size,
                Listing.product_url,
                Listing.last_checked_at,
            )
            .select_from(PriceSnapshot)
            .join(Listing, Listing.id == PriceSnapshot.listing_id)
            .join(ProductVariant, ProductVariant.id == PriceSnapshot.variant_id)
            .join(Retailer, Retailer.id == Listing.retailer_id)
            .where(*self._history_filters(product_id, params))
            .distinct()
            .order_by(Retailer.name, ProductVariant.color, ProductVariant.size)
        ).mappings()
        return [
            ProductOfferHistory.model_validate(
                {**row, "price_history": [], "inventory_history": []}
            )
            for row in rows
        ]

    def _price_history(
        self,
        session: Session,
        product_id: int,
        params: ProductHistoryParams,
    ) -> list[Any]:
        ranked = (
            select(
                PriceSnapshot.listing_id,
                PriceSnapshot.variant_id,
                PriceSnapshot.current_price,
                PriceSnapshot.original_price,
                PriceSnapshot.discount_percentage,
                PriceSnapshot.currency,
                PriceSnapshot.checked_at,
                func.row_number()
                .over(
                    partition_by=(PriceSnapshot.listing_id, PriceSnapshot.variant_id),
                    order_by=(PriceSnapshot.checked_at.desc(), PriceSnapshot.id.desc()),
                )
                .label("history_rank"),
            )
            .join(Listing, Listing.id == PriceSnapshot.listing_id)
            .join(ProductVariant, ProductVariant.id == PriceSnapshot.variant_id)
            .join(Retailer, Retailer.id == Listing.retailer_id)
            .where(*self._history_filters(product_id, params))
            .subquery("ranked_price_history")
        )
        return list(
            session.execute(
                select(ranked)
                .where(ranked.c.history_rank <= params.limit_per_offer)
                .order_by(
                    ranked.c.listing_id,
                    ranked.c.variant_id,
                    ranked.c.checked_at,
                    ranked.c.history_rank.desc(),
                )
            ).mappings()
        )

    def _inventory_history(
        self,
        session: Session,
        product_id: int,
        params: ProductHistoryParams,
    ) -> list[Any]:
        ranked = (
            select(
                InventorySnapshot.listing_id,
                InventorySnapshot.variant_id,
                InventorySnapshot.stock_status,
                InventorySnapshot.checked_at,
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
                .label("history_rank"),
            )
            .join(Listing, Listing.id == InventorySnapshot.listing_id)
            .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
            .join(Retailer, Retailer.id == Listing.retailer_id)
            .where(*self._history_filters(product_id, params))
            .subquery("ranked_inventory_history")
        )
        return list(
            session.execute(
                select(ranked)
                .where(ranked.c.history_rank <= params.limit_per_offer)
                .order_by(
                    ranked.c.listing_id,
                    ranked.c.variant_id,
                    ranked.c.checked_at,
                    ranked.c.history_rank.desc(),
                )
            ).mappings()
        )
