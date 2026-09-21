import json
import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from app.adapters.base import ConfiguredUrlAdapter
from app.adapters.errors import AdapterParseError
from app.schemas.retailer import RetailerListing
from app.services.normalization import StockStatus, parse_price


class MonodSportsAdapter(ConfiguredUrlAdapter):
    """Parse Monod Sports Shopify ProductGroup and analytics JSON."""

    retailer_name = "Monod Sports"
    _allowed_hosts = {"monodsports.com", "www.monodsports.com"}
    _availability_map = {
        "https://schema.org/InStock": StockStatus.AVAILABLE,
        "http://schema.org/InStock": StockStatus.AVAILABLE,
        "https://schema.org/LimitedAvailability": StockStatus.AVAILABLE,
        "http://schema.org/LimitedAvailability": StockStatus.AVAILABLE,
        "https://schema.org/OutOfStock": StockStatus.OUT_OF_STOCK,
        "http://schema.org/OutOfStock": StockStatus.OUT_OF_STOCK,
    }

    @classmethod
    def _validate_product_url(cls, url: str) -> str:
        parsed = urlsplit(url)
        path = parsed.path
        valid_path = path.startswith("/products/") or re.match(
            r"^/[a-z]{2}-[a-z]{2}/products/", path
        )
        if (
            parsed.scheme != "https"
            or parsed.hostname not in cls._allowed_hosts
            or not valid_path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Monod Sports URLs must be query-free HTTPS product pages"
            )
        return url

    def parse_product_page(
        self,
        html: str,
        *,
        product_url: str,
        checked_at: datetime,
    ) -> Sequence[RetailerListing]:
        safe_url = self._validate_product_url(product_url)
        soup = BeautifulSoup(html, "html.parser")
        product = self._find_product_group(soup)
        product_name = self._required_text(product, "name", "product name")
        canonical_name = self._canonical_product_name(product_name)
        raw_variants = product.get("hasVariant")
        if not isinstance(raw_variants, list) or not raw_variants:
            raise AdapterParseError("Monod Sports product data contains no variants")

        analytics = self._analytics_variants(soup)
        selected = self._selected_variant_data(soup)
        style_number = self._extract_style_number(soup)
        listings: list[RetailerListing] = []
        for position, raw_variant in enumerate(raw_variants, start=1):
            if not isinstance(raw_variant, Mapping):
                raise AdapterParseError(f"Monod Sports variant {position} is not an object")
            try:
                sku = self._required_text(raw_variant, "sku", f"variant {position} SKU")
                offer = raw_variant.get("offers")
                if not isinstance(offer, Mapping):
                    raise AdapterParseError(
                        f"Monod Sports variant {position} is missing its offer"
                    )
                color, size = self._variant_options(
                    raw_variant,
                    product_name=product_name,
                    analytics=analytics.get(sku),
                    position=position,
                )
                current_price = offer.get("price")
                if current_price is None:
                    raise AdapterParseError(
                        f"Monod Sports variant {position} is missing current price"
                    )
                original_price = self._original_price(selected.get(sku), current_price)
                availability = offer.get("availability")
                image_url = raw_variant.get("image")
                if not isinstance(image_url, str):
                    image_url = None
                listings.append(
                    RetailerListing.model_validate(
                        {
                            "brand": "Arc'teryx",
                            "product_name": canonical_name,
                            "model_number": style_number,
                            "style_number": style_number,
                            "retailer": self.retailer_name,
                            "current_price": current_price,
                            "original_price": original_price,
                            "currency": offer.get("priceCurrency", "CAD"),
                            "color": color,
                            "size": size,
                            "stock_status": self._availability_map.get(
                                availability, StockStatus.UNKNOWN
                            ),
                            "product_url": safe_url,
                            "image_url": image_url,
                            "variant_sku": sku,
                            "checked_at": checked_at,
                        }
                    )
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise AdapterParseError(
                    f"Monod Sports variant {position} is invalid: {error}"
                ) from error
        return listings

    @classmethod
    def _find_product_group(cls, soup: BeautifulSoup) -> Mapping[str, Any]:
        saw_invalid = False
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if not isinstance(script, Tag):
                continue
            try:
                document = json.loads(script.string or script.get_text())
            except json.JSONDecodeError:
                saw_invalid = True
                continue
            for candidate in cls._walk_objects(document):
                if candidate.get("@type") == "ProductGroup":
                    return candidate
        detail = "invalid JSON-LD" if saw_invalid else "missing ProductGroup JSON-LD"
        raise AdapterParseError(f"Monod Sports product page has {detail}")

    @classmethod
    def _analytics_variants(cls, soup: BeautifulSoup) -> dict[str, Mapping[str, Any]]:
        pattern = re.compile(r"\bvar\s+meta\s*=\s*(\{.*?\});", re.DOTALL)
        for script in soup.find_all("script"):
            raw = script.string or script.get_text()
            if "ShopifyAnalytics.meta" not in raw or '"variants"' not in raw:
                continue
            match = pattern.search(raw)
            if not match:
                continue
            try:
                document = json.loads(match.group(1))
            except json.JSONDecodeError as error:
                raise AdapterParseError(
                    "Monod Sports Shopify analytics data is invalid JSON"
                ) from error
            variants = document.get("product", {}).get("variants", [])
            if isinstance(variants, list):
                return {
                    str(item["sku"]): item
                    for item in variants
                    if isinstance(item, Mapping) and item.get("sku")
                }
        return {}

    @staticmethod
    def _selected_variant_data(soup: BeautifulSoup) -> dict[str, Mapping[str, Any]]:
        values: dict[str, Mapping[str, Any]] = {}
        for script in soup.find_all("script", attrs={"data-variant": True}):
            raw = script.string or script.get_text()
            try:
                variant = json.loads(raw)
            except json.JSONDecodeError as error:
                raise AdapterParseError(
                    "Monod Sports selected variant data is invalid JSON"
                ) from error
            if isinstance(variant, Mapping) and variant.get("sku"):
                values[str(variant["sku"])] = variant
        return values

    @staticmethod
    def _variant_options(
        variant: Mapping[str, Any],
        *,
        product_name: str,
        analytics: Mapping[str, Any] | None,
        position: int,
    ) -> tuple[str, str]:
        title = analytics.get("public_title") if analytics else None
        if not isinstance(title, str):
            title = variant.get("name")
            if isinstance(title, str) and title.startswith(f"{product_name} - "):
                title = title[len(product_name) + 3 :]
        if not isinstance(title, str) or " / " not in title:
            raise AdapterParseError(
                f"Monod Sports variant {position} is missing colour or size"
            )
        color, size = title.rsplit(" / ", 1)
        return color, size

    @staticmethod
    def _original_price(
        selected_variant: Mapping[str, Any] | None, current_price: object
    ) -> Decimal | None:
        if not selected_variant:
            return None
        raw = selected_variant.get("compare_at_price")
        if raw is None:
            return None
        original = parse_price(Decimal(str(raw)) / Decimal("100"))
        current = parse_price(current_price)  # type: ignore[arg-type]
        return original if original > current else None

    @classmethod
    def _walk_objects(cls, value: object) -> Iterator[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            yield value
            for child in value.values():
                yield from cls._walk_objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_objects(child)

    @staticmethod
    def _required_text(data: Mapping[str, Any], key: str, label: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AdapterParseError(f"Monod Sports data is missing {label}")
        return value.strip()

    @staticmethod
    def _extract_style_number(soup: BeautifulSoup) -> str | None:
        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"\b(?:Style\s*#|Model)\s*:?[ ]*(X\d{9})\b",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).upper() if match else None

    @staticmethod
    def _canonical_product_name(product_name: str) -> str:
        value = re.sub(
            r"\s*\((?:Past|Prior) Season\)\s*", " ", product_name, flags=re.IGNORECASE
        ).strip()
        match = re.match(r"^(Men|Women)(?:'s|s)\s+(.+)$", value, flags=re.IGNORECASE)
        if match:
            gender = "Men's" if match.group(1).casefold() == "men" else "Women's"
            value = f"{match.group(2)} {gender}"
        return f"Arc'teryx {value}"
