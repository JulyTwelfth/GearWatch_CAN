import json
import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from app.adapters.base import ConfiguredUrlAdapter
from app.adapters.errors import AdapterParseError
from app.schemas.retailer import RetailerListing
from app.services.normalization import StockStatus, normalize_lookup_key


class VpoAdapter(ConfiguredUrlAdapter):
    """Parse Valhalla Pure Outfitters public Product/Offer JSON-LD."""

    retailer_name = "Valhalla Pure Outfitters"
    _allowed_hosts = {"vpo.ca", "www.vpo.ca"}
    _available_values = {
        "https://schema.org/InStock",
        "http://schema.org/InStock",
        "https://schema.org/LimitedAvailability",
        "http://schema.org/LimitedAvailability",
    }
    _out_values = {
        "https://schema.org/OutOfStock",
        "http://schema.org/OutOfStock",
    }

    @classmethod
    def _validate_product_url(cls, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in cls._allowed_hosts
            or not parsed.path.startswith("/products/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("VPO URLs must be query-free HTTPS product pages")
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
        product = self._find_product(soup)
        brand = product.get("brand")
        brand_name = brand.get("name") if isinstance(brand, Mapping) else brand
        if not isinstance(brand_name, str) or normalize_lookup_key(brand_name) != "arcteryx":
            raise AdapterParseError("VPO configured page is not an Arc'teryx product")

        product_name = self._required_text(product, "name", "product name")
        offers = product.get("offers")
        if isinstance(offers, Mapping):
            offers = [offers]
        if not isinstance(offers, list) or not offers:
            raise AdapterParseError("VPO product data contains no offers")

        style_number = self._extract_style_number(soup)
        image_url = self._first_image(product.get("image"))
        variant_data = self._variant_data(soup)
        grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
        for position, offer in enumerate(offers, start=1):
            if not isinstance(offer, Mapping):
                raise AdapterParseError(f"VPO offer {position} is not an object")
            sku = self._required_text(offer, "sku", f"offer {position} SKU")
            color, size = self._offer_options(offer)
            grouped.setdefault((sku, color, size), []).append(offer)

        listings: list[RetailerListing] = []
        for (sku, color, size), variant_offers in grouped.items():
            first = variant_offers[0]
            price = first.get("price")
            if price is None:
                raise AdapterParseError(f"VPO variant {sku} is missing current price")
            if any(offer.get("price") != price for offer in variant_offers[1:]):
                raise AdapterParseError(f"VPO variant {sku} has conflicting prices")
            availability = self._aggregate_availability(variant_offers)
            original_price = self._original_price(variant_data.get(sku))
            try:
                listings.append(
                    RetailerListing.model_validate(
                        {
                            "brand": "Arc'teryx",
                            "product_name": f"Arc'teryx {product_name}",
                            "model_number": style_number,
                            "style_number": style_number,
                            "retailer": self.retailer_name,
                            "current_price": price,
                            "original_price": original_price,
                            "currency": first.get("priceCurrency", "CAD"),
                            "color": color,
                            "size": size,
                            "stock_status": availability,
                            "product_url": safe_url,
                            "image_url": image_url,
                            "variant_sku": sku,
                            "checked_at": checked_at,
                        }
                    )
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise AdapterParseError(f"VPO variant {sku} is invalid: {error}") from error
        return listings

    @staticmethod
    def _variant_data(soup: BeautifulSoup) -> dict[str, Mapping[str, Any]]:
        variants: dict[str, Mapping[str, Any]] = {}
        for tag in soup.find_all(attrs={"data-options": True}):
            raw = tag.get("data-options")
            if not isinstance(raw, str):
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as error:
                raise AdapterParseError("VPO variant data is invalid JSON") from error
            if isinstance(data, Mapping) and data.get("sku"):
                variants[str(data["sku"])] = data
        return variants

    @staticmethod
    def _original_price(variant: Mapping[str, Any] | None) -> object | None:
        if variant is None:
            return None
        value = variant.get("compareAtPrice")
        if not isinstance(value, Mapping):
            return None
        return value.get("amount")

    @classmethod
    def _find_product(cls, soup: BeautifulSoup) -> Mapping[str, Any]:
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
                if candidate.get("@type") == "Product":
                    return candidate
        detail = "invalid JSON-LD" if saw_invalid else "missing Product JSON-LD"
        raise AdapterParseError(f"VPO product page has {detail}")

    @staticmethod
    def _offer_options(offer: Mapping[str, Any]) -> tuple[str, str]:
        url = offer.get("url")
        if not isinstance(url, str):
            return "Unknown", "ONE SIZE"
        values = parse_qs(urlsplit(url).query)
        color = values.get("Color", values.get("Colour", ["Unknown"]))[0]
        size = values.get("Size", ["ONE SIZE"])[0]
        return color or "Unknown", size or "ONE SIZE"

    @classmethod
    def _aggregate_availability(
        cls, offers: Sequence[Mapping[str, Any]]
    ) -> StockStatus:
        values = {offer.get("availability") for offer in offers}
        if values & cls._available_values:
            return StockStatus.AVAILABLE
        if values and values <= cls._out_values:
            return StockStatus.OUT_OF_STOCK
        return StockStatus.UNKNOWN

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
    def _first_image(value: object) -> str | None:
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, Mapping):
            value = value.get("url") or value.get("contentUrl")
        return value if isinstance(value, str) and value.startswith("https://") else None

    @staticmethod
    def _required_text(data: Mapping[str, Any], key: str, label: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AdapterParseError(f"VPO data is missing {label}")
        return value.strip()

    @staticmethod
    def _extract_style_number(soup: BeautifulSoup) -> str | None:
        text = soup.get_text(" ", strip=True)
        match = re.search(
            r"\bArcteryx\s+Part\s*#\s*([A-Z0-9._-]{3,})\b",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).upper() if match else None
