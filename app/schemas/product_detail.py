from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.services.normalization import StockStatus


class ProductHistoryParams(BaseModel):
    listing_id: int | None = Field(default=None, gt=0)
    variant_id: int | None = Field(default=None, gt=0)
    limit_per_offer: int = Field(default=50, ge=1, le=200)

    model_config = ConfigDict(extra="forbid")


class CurrentProductOffer(BaseModel):
    listing_id: int
    variant_id: int
    retailer: str
    current_price: Decimal
    original_price: Decimal | None
    discount_percentage: Decimal
    currency: str
    color: str
    size: str
    stock_status: StockStatus
    product_url: HttpUrl
    source_status: str = "success"
    status_checked_at: datetime | None = None
    last_checked_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProductDetailResponse(BaseModel):
    product_id: int
    brand: str
    product_name: str
    model_number: str | None
    model_name: str | None = None
    style_number: str | None = None
    gender: str = "Unknown"
    category: str = "Other"
    image_url: HttpUrl | None = None
    last_checked_at: datetime | None
    offers: list[CurrentProductOffer]

    model_config = ConfigDict(extra="forbid")


class PriceHistoryPoint(BaseModel):
    current_price: Decimal
    original_price: Decimal | None
    discount_percentage: Decimal
    currency: str
    checked_at: datetime

    model_config = ConfigDict(extra="forbid")


class InventoryHistoryPoint(BaseModel):
    stock_status: StockStatus
    checked_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProductOfferHistory(BaseModel):
    listing_id: int
    variant_id: int
    retailer: str
    color: str
    size: str
    product_url: HttpUrl
    last_checked_at: datetime
    price_history: list[PriceHistoryPoint]
    inventory_history: list[InventoryHistoryPoint]

    model_config = ConfigDict(extra="forbid")


class ProductHistoryResponse(BaseModel):
    product_id: int
    brand: str
    product_name: str
    model_number: str | None
    model_name: str | None = None
    style_number: str | None = None
    gender: str = "Unknown"
    category: str = "Other"
    image_url: HttpUrl | None = None
    limit_per_offer: int
    offers: list[ProductOfferHistory]

    model_config = ConfigDict(extra="forbid")
