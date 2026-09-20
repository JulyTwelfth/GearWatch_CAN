import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Listing,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.schemas.retailer import RetailerListing
from app.services.normalization import normalize_lookup_key


@dataclass(frozen=True, slots=True)
class IngestResult:
    product_id: int
    retailer_id: int
    listing_id: int
    variant_id: int
    price_snapshot_created: bool
    inventory_snapshot_created: bool


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _get_or_create_retailer(session: Session, data: RetailerListing) -> Retailer:
    slug = normalize_lookup_key(data.retailer)
    retailer = session.scalar(select(Retailer).where(Retailer.slug == slug))
    if retailer is None:
        retailer = Retailer(name=data.retailer, slug=slug)
        session.add(retailer)
        session.flush()
    return retailer


def _get_or_create_product(session: Session, data: RetailerListing) -> Product:
    normalized_name = normalize_lookup_key(data.product_name)
    normalized_model = data.model_number.casefold() if data.model_number else None

    product = None
    if normalized_model:
        product = session.scalar(
            select(Product).where(
                Product.brand == data.brand,
                Product.normalized_model_number == normalized_model,
            )
        )
        if product is None:
            product = session.scalar(
                select(Product).where(
                    Product.brand == data.brand,
                    Product.normalized_name == normalized_name,
                    Product.normalized_model_number.is_(None),
                )
            )
            if product is not None:
                product.model_number = data.model_number
                product.normalized_model_number = normalized_model
                product.identity_key = f"model:{normalized_model}"
    else:
        candidates = session.scalars(
            select(Product)
            .where(
                Product.brand == data.brand,
                Product.normalized_name == normalized_name,
            )
            .limit(2)
        ).all()
        if len(candidates) == 1:
            product = candidates[0]

    if product is None:
        identity_key = (
            f"model:{normalized_model}" if normalized_model else f"name:{normalized_name}"
        )
        product = Product(
            brand=data.brand,
            name=data.product_name,
            normalized_name=normalized_name,
            model_number=data.model_number,
            normalized_model_number=normalized_model,
            identity_key=identity_key,
        )
        session.add(product)
        session.flush()
    return product


def _get_or_create_listing(
    session: Session,
    data: RetailerListing,
    product: Product,
    retailer: Retailer,
) -> Listing:
    product_url = str(data.product_url)
    url_hash = _url_hash(product_url)
    listing = session.scalar(
        select(Listing).where(
            Listing.retailer_id == retailer.id,
            Listing.url_hash == url_hash,
        )
    )
    if listing is None:
        listing = Listing(
            product_id=product.id,
            retailer_id=retailer.id,
            product_url=product_url,
            url_hash=url_hash,
            currency=data.currency,
            last_checked_at=data.checked_at,
        )
        session.add(listing)
        session.flush()
    elif data.checked_at > listing.last_checked_at:
        listing.last_checked_at = data.checked_at
    return listing


def _get_or_create_variant(
    session: Session, data: RetailerListing, product: Product
) -> ProductVariant:
    normalized_color = normalize_lookup_key(data.color)
    normalized_size = normalize_lookup_key(data.size)
    variant = session.scalar(
        select(ProductVariant).where(
            ProductVariant.product_id == product.id,
            ProductVariant.normalized_color == normalized_color,
            ProductVariant.normalized_size == normalized_size,
        )
    )
    if variant is None:
        variant = ProductVariant(
            product_id=product.id,
            color=data.color,
            normalized_color=normalized_color,
            size=data.size,
            normalized_size=normalized_size,
        )
        session.add(variant)
        session.flush()
    return variant


def _create_price_snapshot_if_changed(
    session: Session,
    data: RetailerListing,
    listing: Listing,
    variant: ProductVariant,
) -> bool:
    same_point = session.scalar(
        select(PriceSnapshot.id).where(
            PriceSnapshot.listing_id == listing.id,
            PriceSnapshot.variant_id == variant.id,
            PriceSnapshot.checked_at == data.checked_at,
        )
    )
    if same_point is not None:
        return False

    latest = session.scalar(
        select(PriceSnapshot)
        .where(
            PriceSnapshot.listing_id == listing.id,
            PriceSnapshot.variant_id == variant.id,
        )
        .order_by(PriceSnapshot.checked_at.desc())
        .limit(1)
    )
    unchanged = latest is not None and (
        latest.current_price == data.current_price
        and latest.original_price == data.original_price
        and latest.currency == data.currency
    )
    if unchanged:
        return False

    session.add(
        PriceSnapshot(
            listing_id=listing.id,
            variant_id=variant.id,
            current_price=data.current_price,
            original_price=data.original_price,
            discount_percentage=data.discount_percentage,
            currency=data.currency,
            checked_at=data.checked_at,
        )
    )
    return True


def _create_inventory_snapshot_if_changed(
    session: Session,
    data: RetailerListing,
    listing: Listing,
    variant: ProductVariant,
) -> bool:
    same_point = session.scalar(
        select(InventorySnapshot.id).where(
            InventorySnapshot.listing_id == listing.id,
            InventorySnapshot.variant_id == variant.id,
            InventorySnapshot.checked_at == data.checked_at,
        )
    )
    if same_point is not None:
        return False

    latest = session.scalar(
        select(InventorySnapshot)
        .where(
            InventorySnapshot.listing_id == listing.id,
            InventorySnapshot.variant_id == variant.id,
        )
        .order_by(InventorySnapshot.checked_at.desc())
        .limit(1)
    )
    if latest is not None and latest.stock_status == data.stock_status:
        return False

    session.add(
        InventorySnapshot(
            listing_id=listing.id,
            variant_id=variant.id,
            stock_status=data.stock_status,
            checked_at=data.checked_at,
        )
    )
    return True


def ingest_retailer_listing(session: Session, data: RetailerListing) -> IngestResult:
    """Persist one validated adapter row and append snapshots only for changed values."""
    retailer = _get_or_create_retailer(session, data)
    product = _get_or_create_product(session, data)
    listing = _get_or_create_listing(session, data, product, retailer)
    variant = _get_or_create_variant(session, data, product)

    price_created = _create_price_snapshot_if_changed(session, data, listing, variant)
    inventory_created = _create_inventory_snapshot_if_changed(session, data, listing, variant)
    session.flush()

    return IngestResult(
        product_id=product.id,
        retailer_id=retailer.id,
        listing_id=listing.id,
        variant_id=variant.id,
        price_snapshot_created=price_created,
        inventory_snapshot_created=inventory_created,
    )
