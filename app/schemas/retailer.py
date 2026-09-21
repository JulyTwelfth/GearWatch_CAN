from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator, model_validator

from app.services.normalization import (
    ProductGender,
    StockStatus,
    calculate_discount,
    derive_model_name,
    infer_category,
    infer_gender,
    normalize_brand,
    normalize_color,
    normalize_gender,
    normalize_model_number,
    normalize_product_name,
    normalize_size,
    normalize_stock_status,
    normalize_text,
    parse_price,
)


class RetailerListing(BaseModel):
    """Canonical output produced by every retailer adapter for one variant."""

    brand: str
    product_name: str
    model_number: str | None = None
    model_name: str | None = None
    style_number: str | None = None
    gender: ProductGender = ProductGender.UNKNOWN
    category: str = "Other"
    retailer: str
    current_price: Decimal
    original_price: Decimal | None = None
    discount_percentage: Decimal = Decimal("0.00")
    currency: Literal["CAD"] = "CAD"
    color: str
    size: str
    stock_status: StockStatus
    product_url: HttpUrl
    image_url: HttpUrl | None = None
    variant_sku: str | None = None
    checked_at: datetime

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("brand", mode="before")
    @classmethod
    def validate_brand(cls, value: str) -> str:
        normalized = normalize_brand(value)
        if not normalized:
            raise ValueError("brand cannot be empty")
        return normalized

    @field_validator("product_name", mode="before")
    @classmethod
    def validate_product_name(cls, value: str) -> str:
        normalized = normalize_product_name(value)
        if not normalized:
            raise ValueError("product name cannot be empty")
        return normalized

    @field_validator("model_number", "style_number", mode="before")
    @classmethod
    def validate_model_number(cls, value: str | None) -> str | None:
        return normalize_model_number(value)

    @field_validator("model_name", mode="before")
    @classmethod
    def validate_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_text(value)
        return normalized or None

    @field_validator("gender", mode="before")
    @classmethod
    def validate_gender(cls, value: str | ProductGender | None) -> ProductGender:
        return normalize_gender(value)

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, value: str | None) -> str:
        normalized = normalize_text(value or "")
        return normalized or "Other"

    @field_validator("variant_sku", mode="before")
    @classmethod
    def validate_variant_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_text(value)
        return normalized or None

    @field_validator("retailer", mode="before")
    @classmethod
    def validate_retailer(cls, value: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("retailer cannot be empty")
        return normalized

    @field_validator("current_price", "original_price", mode="before")
    @classmethod
    def validate_price(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_price(value)  # type: ignore[arg-type]

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_text(value).upper()

    @field_validator("color", mode="before")
    @classmethod
    def validate_color(cls, value: str) -> str:
        return normalize_color(value)

    @field_validator("size", mode="before")
    @classmethod
    def validate_size(cls, value: str) -> str:
        return normalize_size(value)

    @field_validator("stock_status", mode="before")
    @classmethod
    def validate_stock_status(cls, value: str | bool | int | None) -> StockStatus:
        return normalize_stock_status(value)

    @field_validator("checked_at")
    @classmethod
    def validate_checked_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checked_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_prices_and_discount(self) -> Self:
        if self.style_number is None:
            self.style_number = self.model_number
        if self.model_number is None:
            self.model_number = self.style_number
        if self.model_name is None:
            self.model_name = derive_model_name(self.product_name)
        if self.gender is ProductGender.UNKNOWN:
            self.gender = infer_gender(self.product_name, str(self.product_url))
        if self.category == "Other":
            self.category = infer_category(self.product_name)
        if self.original_price is not None and self.original_price < self.current_price:
            raise ValueError("original price cannot be lower than current price")
        self.discount_percentage = calculate_discount(self.current_price, self.original_price)
        return self
