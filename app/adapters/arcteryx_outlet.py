import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from app.adapters.base import ConfiguredUrlAdapter
from app.adapters.errors import AdapterParseError
from app.schemas.retailer import RetailerListing
from app.services.normalization import StockStatus, parse_price


class ArcTeryxOutletAdapter(ConfiguredUrlAdapter):
    """Collect explicitly configured Arc'teryx Outlet Canada product pages."""

    retailer_name = "Arc'teryx Outlet Canada"
    _allowed_host = "outlet.arcteryx.com"
    _allowed_path_prefix = "/ca/en/shop/"
    _availability_map = {
        "https://schema.org/InStock": StockStatus.AVAILABLE,
        "https://schema.org/LimitedAvailability": StockStatus.AVAILABLE,
        "https://schema.org/OutOfStock": StockStatus.OUT_OF_STOCK,
        "http://schema.org/InStock": StockStatus.AVAILABLE,
        "http://schema.org/LimitedAvailability": StockStatus.AVAILABLE,
        "http://schema.org/OutOfStock": StockStatus.OUT_OF_STOCK,
    }

    def parse_product_page(
        self,
        html: str,
        *,
        product_url: str,
        checked_at: datetime,
    ) -> list[RetailerListing]:
        safe_product_url = self._validate_product_url(product_url)
        soup = BeautifulSoup(html, "html.parser")
        product_group = self._find_product_group(soup)
        product_name = self._required_text_value(product_group, "name", "product name")
        model_number = self._required_text_value(
            product_group, "productGroupID", "product model number"
        )
        original_prices = self._original_prices_by_sku(soup)

        raw_variants = product_group.get("hasVariant")
        if not isinstance(raw_variants, list) or not raw_variants:
            raise AdapterParseError("Arc'teryx Outlet product data contains no variants")

        listings: list[RetailerListing] = []
        for position, raw_variant in enumerate(raw_variants, start=1):
            if not isinstance(raw_variant, Mapping):
                raise AdapterParseError(
                    f"Arc'teryx Outlet variant {position} is not an object"
                )
            try:
                sku = self._required_text_value(raw_variant, "sku", f"variant {position} SKU")
                color = self._required_text_value(
                    raw_variant, "color", f"variant {position} color"
                )
                size = self._required_text_value(
                    raw_variant, "size", f"variant {position} size"
                )
                offer = self._required_offer(raw_variant, position)
                current_price = self._required_value(
                    offer, "price", f"variant {position} current price"
                )
                currency = self._required_text_value(
                    offer, "priceCurrency", f"variant {position} currency"
                )
                availability = offer.get("availability")
                stock_status = (
                    self._availability_map.get(availability, StockStatus.UNKNOWN)
                    if isinstance(availability, str)
                    else StockStatus.UNKNOWN
                )
                original_price = self._sale_original_price(
                    original_prices.get(sku), current_price
                )

                listings.append(
                    RetailerListing.model_validate(
                        {
                            "brand": "Arc'teryx",
                            "product_name": product_name,
                            "model_number": model_number,
                            "style_number": model_number,
                            "retailer": self.retailer_name,
                            "current_price": current_price,
                            "original_price": original_price,
                            "currency": currency,
                            "color": color,
                            "size": size,
                            "stock_status": stock_status,
                            "product_url": safe_product_url,
                            "image_url": self._image_value(raw_variant, product_group),
                            "variant_sku": sku,
                            "checked_at": checked_at,
                        }
                    )
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise AdapterParseError(
                    f"Arc'teryx Outlet variant {position} is invalid: {error}"
                ) from error
        return listings

    @staticmethod
    def _image_value(
        variant: Mapping[str, Any], product_group: Mapping[str, Any]
    ) -> str | None:
        value = variant.get("image") or product_group.get("image")
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, Mapping):
            value = value.get("url") or value.get("contentUrl")
        return value if isinstance(value, str) and value.startswith("https://") else None

    @classmethod
    def _validate_product_url(cls, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != cls._allowed_host
            or not parsed.path.startswith(cls._allowed_path_prefix)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Arc'teryx Outlet URLs must be query-free Canadian HTTPS product pages"
            )
        return url

    @classmethod
    def _find_product_group(cls, soup: BeautifulSoup) -> Mapping[str, Any]:
        saw_invalid_json = False
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not isinstance(script, Tag):
                continue
            raw_json = script.string or script.get_text()
            if not raw_json.strip():
                continue
            try:
                document = json.loads(raw_json)
            except json.JSONDecodeError:
                saw_invalid_json = True
                continue
            for candidate in cls._walk_objects(document):
                item_types = candidate.get("@type")
                if item_types == "ProductGroup" or (
                    isinstance(item_types, list) and "ProductGroup" in item_types
                ):
                    return candidate

        detail = (
            " contains invalid JSON-LD"
            if saw_invalid_json
            else " is missing ProductGroup JSON-LD"
        )
        raise AdapterParseError(f"Arc'teryx Outlet product page{detail}")

    @classmethod
    def _original_prices_by_sku(cls, soup: BeautifulSoup) -> dict[str, object]:
        script = soup.find("script", id="__NEXT_DATA__")
        if not isinstance(script, Tag):
            return {}
        raw_json = script.string or script.get_text()
        if not raw_json.strip():
            return {}
        try:
            document = json.loads(raw_json)
        except json.JSONDecodeError as error:
            raise AdapterParseError("Arc'teryx Outlet __NEXT_DATA__ is invalid JSON") from error

        prices: dict[str, object] = {}
        for candidate in cls._walk_objects(document):
            variant_id = candidate.get("id")
            if isinstance(variant_id, str) and "price" in candidate:
                prices[variant_id] = candidate["price"]
        return prices

    @classmethod
    def _walk_objects(cls, value: object) -> Iterator[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            yield value
            for child in value.values():
                yield from cls._walk_objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_objects(child)
        elif isinstance(value, str):
            serialized = value.strip()
            if serialized.startswith(("{", "[")):
                try:
                    embedded = json.loads(serialized)
                except json.JSONDecodeError:
                    return
                yield from cls._walk_objects(embedded)

    @staticmethod
    def _required_offer(variant: Mapping[str, Any], position: int) -> Mapping[str, Any]:
        offer = variant.get("offers")
        if isinstance(offer, list):
            offer = offer[0] if offer else None
        if not isinstance(offer, Mapping):
            raise AdapterParseError(
                f"Arc'teryx Outlet variant {position} is missing its offer"
            )
        return offer

    @staticmethod
    def _required_text_value(data: Mapping[str, Any], key: str, label: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AdapterParseError(f"Arc'teryx Outlet data is missing {label}")
        return value

    @staticmethod
    def _required_value(data: Mapping[str, Any], key: str, label: str) -> object:
        value = data.get(key)
        if value is None:
            raise AdapterParseError(f"Arc'teryx Outlet data is missing {label}")
        return value

    @staticmethod
    def _sale_original_price(original_price: object | None, current_price: object) -> object | None:
        if original_price is None:
            return None
        original = parse_price(original_price)  # type: ignore[arg-type]
        current = parse_price(current_price)  # type: ignore[arg-type]
        return original if original > current else None
