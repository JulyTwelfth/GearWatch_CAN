from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.services.normalization import StockStatus, normalize_lookup_key


class ProductSearchParams(BaseModel):
    q: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=3, max_length=100)
    size: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, min_length=1, max_length=150)
    min_discount: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    stock_status: StockStatus | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("q", "model", "size", "color")
    @classmethod
    def validate_search_text(cls, value: str | None) -> str | None:
        if value is not None and not normalize_lookup_key(value):
            raise ValueError("search text must contain a letter or number")
        return value


class ProductOfferRead(BaseModel):
    product_id: int
    brand: str
    product_name: str
    model_number: str | None
    retailer: str
    current_price: Decimal
    original_price: Decimal | None
    discount_percentage: Decimal
    currency: str
    color: str
    size: str
    stock_status: StockStatus
    product_url: HttpUrl
    last_checked_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProductSearchResponse(BaseModel):
    items: list[ProductOfferRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")
