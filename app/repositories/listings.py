import hashlib
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FetchStatus,
    InventorySnapshot,
    Listing,
    ListingVariant,
    PriceSnapshot,
    Product,
    ProductVariant,
    Retailer,
)
from app.schemas.retailer import RetailerListing
from app.services.normalization import normalize_lookup_key
from app.services.product_matching import canonical_model_key


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


def _get_or_create_retailer_by_name(
    session: Session, retailer_name: str, source_url: str | None = None
) -> Retailer:
    slug = normalize_lookup_key(retailer_name)
    retailer = session.scalar(select(Retailer).where(Retailer.slug == slug))
    if retailer is None:
        base_url = None
        if source_url:
            parsed = urlsplit(source_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        retailer = Retailer(name=retailer_name, slug=slug, base_url=base_url)
        session.add(retailer)
        session.flush()
    return retailer


def _get_or_create_retailer(session: Session, data: RetailerListing) -> Retailer:
    return _get_or_create_retailer_by_name(session, data.retailer, str(data.product_url))


def _get_or_create_product(session: Session, data: RetailerListing) -> Product:
    normalized_name = normalize_lookup_key(data.product_name)
    normalized_style = data.style_number.casefold() if data.style_number else None
    normalized_model_name = canonical_model_key(data.model_name or data.product_name)
    gender = data.gender.value
    category_key = normalize_lookup_key(data.category) or "other"

    product = None
    if normalized_style:
        product = session.scalar(
            select(Product).where(
                Product.brand == data.brand,
                (
                    (Product.normalized_style_number == normalized_style)
                    | (Product.normalized_model_number == normalized_style)
                ),
            )
        )
    if product is None and normalized_model_name:
        model_filters = [
            Product.brand == data.brand,
            Product.normalized_model_name == normalized_model_name,
            Product.gender.in_((gender, "Unknown")),
        ]
        if data.category != "Other":
            model_filters.append(Product.category.in_((data.category, "Other")))
        if normalized_style:
            model_filters.extend(
                [
                    Product.normalized_style_number.is_(None),
                    Product.normalized_model_number.is_(None),
                ]
            )
        candidates = session.scalars(
            select(Product)
            .where(*model_filters)
            .limit(2)
        ).all()
        if len(candidates) == 1:
            product = candidates[0]

    if product is None:
        identity_key = (
            f"style:{normalized_style}"
            if normalized_style
            else f"catalog:{normalized_model_name}:{gender.casefold()}:{category_key}"
        )
        product = Product(
            brand=data.brand,
            name=data.product_name,
            normalized_name=normalized_name,
            model_number=data.style_number,
            normalized_model_number=normalized_style,
            model_name=data.model_name,
            normalized_model_name=normalized_model_name,
            style_number=data.style_number,
            normalized_style_number=normalized_style,
            gender=gender,
            category=data.category,
            canonical_url=str(data.product_url),
            image_url=str(data.image_url) if data.image_url else None,
            identity_key=identity_key,
        )
        session.add(product)
        session.flush()
    else:
        if normalized_style and product.normalized_style_number is None:
            product.style_number = data.style_number
            product.normalized_style_number = normalized_style
            product.model_number = data.style_number
            product.normalized_model_number = normalized_style
            product.identity_key = f"style:{normalized_style}"
        if product.normalized_model_name is None:
            product.model_name = data.model_name
            product.normalized_model_name = normalized_model_name
        elif product.model_name and product.model_name.casefold().startswith(
            ("men's ", "womens ", "women's ", "mens ")
        ):
            product.name = data.product_name
            product.normalized_name = normalized_name
            product.model_name = data.model_name
            product.normalized_model_name = normalized_model_name
        if product.gender == "Unknown" and gender != "Unknown":
            product.gender = gender
        if product.category == "Other" and data.category != "Other":
            product.category = data.category
        if product.image_url is None and data.image_url:
            product.image_url = str(data.image_url)
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
            source_status="success",
            status_checked_at=data.checked_at,
        )
        session.add(listing)
        session.flush()
    elif data.checked_at > listing.last_checked_at:
        listing.last_checked_at = data.checked_at
        listing.status_checked_at = data.checked_at
        listing.source_status = "success"
        listing.last_error_type = None
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


def _get_or_create_listing_variant(
    session: Session,
    data: RetailerListing,
    listing: Listing,
    variant: ProductVariant,
) -> ListingVariant:
    link = session.scalar(
        select(ListingVariant).where(
            ListingVariant.listing_id == listing.id,
            ListingVariant.variant_id == variant.id,
        )
    )
    if link is None:
        link = ListingVariant(
            listing_id=listing.id,
            variant_id=variant.id,
            retailer_sku=data.variant_sku,
            is_active=True,
            last_seen_at=data.checked_at,
        )
        session.add(link)
    elif data.checked_at >= link.last_seen_at:
        if data.variant_sku and link.retailer_sku != data.variant_sku:
            link.retailer_sku = data.variant_sku
        link.is_active = True
        link.last_seen_at = data.checked_at
    return link


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
    _get_or_create_listing_variant(session, data, listing, variant)

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


def record_fetch_status(
    session: Session,
    *,
    retailer_name: str,
    source_url: str,
    status: str,
    checked_at: datetime,
    error_type: str | None = None,
) -> bool:
    """Persist one fetch outcome and update an existing listing's source health."""
    retailer = _get_or_create_retailer_by_name(session, retailer_name, source_url)
    url_hash = _url_hash(source_url)
    existing = session.scalar(
        select(FetchStatus.id).where(
            FetchStatus.retailer_id == retailer.id,
            FetchStatus.url_hash == url_hash,
            FetchStatus.checked_at == checked_at,
        )
    )
    if existing is not None:
        return False
    session.add(
        FetchStatus(
            retailer_id=retailer.id,
            source_url=source_url,
            url_hash=url_hash,
            status=status,
            error_type=error_type,
            checked_at=checked_at,
        )
    )
    listing = session.scalar(
        select(Listing).where(
            Listing.retailer_id == retailer.id,
            Listing.url_hash == url_hash,
        )
    )
    if listing is not None and checked_at >= listing.status_checked_at:
        listing.source_status = status
        listing.status_checked_at = checked_at
        listing.last_error_type = error_type
    session.flush()
    return True


def deactivate_missing_listing_variants(
    session: Session,
    *,
    retailer_name: str,
    source_url: str,
    checked_at: datetime,
) -> int:
    """Hide variants not observed in the latest successful page check."""
    listing = session.scalar(
        select(Listing)
        .join(Retailer, Retailer.id == Listing.retailer_id)
        .where(
            Retailer.slug == normalize_lookup_key(retailer_name),
            Listing.url_hash == _url_hash(source_url),
        )
    )
    if listing is None:
        return 0
    stale_links = session.scalars(
        select(ListingVariant).where(
            ListingVariant.listing_id == listing.id,
            ListingVariant.is_active.is_(True),
            ListingVariant.last_seen_at < checked_at,
        )
    ).all()
    for link in stale_links:
        link.is_active = False
    session.flush()
    return len(stale_links)
