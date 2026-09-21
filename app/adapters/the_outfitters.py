import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin, urlsplit

from pydantic import ValidationError

from app.adapters.base import CatalogDiscoveryAdapter, CatalogRequest
from app.adapters.errors import AdapterParseError
from app.schemas.retailer import RetailerListing
from app.services.normalization import StockStatus, normalize_lookup_key


class TheOutfittersAdapter(CatalogDiscoveryAdapter):
    """Collect The Outfitters' public Shopify Arc'teryx catalogue and variants."""

    retailer_name = "The Outfitters"
    _allowed_hosts = {"theoutfitters.nf.ca", "www.theoutfitters.nf.ca"}
    _catalog_url = (
        "https://theoutfitters.nf.ca/collections/arcteryx/products.json"
    )
    _comparison_styles = (
        "X000010511",
        "X000010854",
        "X000009556",
        "X000009561",
        "X000010521",
        "X000010579",
        "X000009905",
        "X000010643",
        "X000009571",
        "X000008436",
        "X000009903",
        "X000010536",
        "X000009906",
        "X000010282",
        "X000009902",
    )

    def catalog_requests(self) -> Sequence[CatalogRequest]:
        return tuple(
            CatalogRequest(
                f"{self._catalog_url}?limit=50&page={page}", content_type="json"
            )
            for page in range(1, self._discovery_max_pages + 1)
        )

    def parse_catalog_page(self, content: str, *, source_url: str) -> Sequence[str]:
        try:
            document = json.loads(content)
        except json.JSONDecodeError as error:
            raise AdapterParseError("The Outfitters catalogue JSON is invalid") from error
        products = document.get("products") if isinstance(document, Mapping) else None
        if not isinstance(products, list):
            raise AdapterParseError("The Outfitters catalogue is missing products")

        urls: list[str] = []
        for product in products:
            if not isinstance(product, Mapping):
                continue
            vendor = product.get("vendor")
            handle = product.get("handle")
            if (
                not isinstance(vendor, str)
                or normalize_lookup_key(vendor) != "arcteryx"
                or not isinstance(handle, str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", handle)
            ):
                continue
            urls.append(
                self._validate_product_url(
                    urljoin("https://theoutfitters.nf.ca/products/", handle)
                )
            )
        return tuple(dict.fromkeys(urls))

    def prioritize_discovered_urls(self, urls: Sequence[str]) -> Sequence[str]:
        def priority(url: str) -> tuple[int, int, int, str]:
            style = self._style_from_text(url)
            if style in self._comparison_styles:
                return (
                    0,
                    self._comparison_styles.index(style),
                    int("past" in url.casefold()),
                    url,
                )
            return (1, len(self._comparison_styles), int("past" in url.casefold()), url)

        return tuple(sorted(urls, key=priority))

    def discovery_identity(self, product_url: str) -> str:
        return self._style_from_text(product_url) or product_url.casefold()

    @classmethod
    def _validate_product_url(cls, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in cls._allowed_hosts
            or not re.fullmatch(r"/products/[a-z0-9][a-z0-9-]*", parsed.path)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "The Outfitters URLs must be query-free HTTPS product pages"
            )
        return url

    def fetch_product(
        self, product_url: str, *, checked_at: datetime | None = None
    ) -> Sequence[RetailerListing]:
        safe_url = self._validate_product_url(product_url)
        product_json = self._http_client.get_json(f"{safe_url}.js")
        return self.parse_product_page(
            product_json,
            product_url=safe_url,
            checked_at=checked_at or self._checked_at_factory(),
        )

    def parse_product_page(
        self,
        html: str,
        *,
        product_url: str,
        checked_at: datetime,
    ) -> Sequence[RetailerListing]:
        safe_url = self._validate_product_url(product_url)
        try:
            product = json.loads(html)
        except json.JSONDecodeError as error:
            raise AdapterParseError("The Outfitters product JSON is invalid") from error
        if not isinstance(product, Mapping):
            raise AdapterParseError("The Outfitters product JSON is not an object")

        vendor = product.get("vendor")
        if not isinstance(vendor, str) or normalize_lookup_key(vendor) != "arcteryx":
            raise AdapterParseError(
                "The Outfitters configured page is not an Arc'teryx product"
            )
        title = self._required_text(product, "title", "product title")
        style_number = self._style_from_text(title) or self._style_from_text(safe_url)
        if style_number is None:
            raise AdapterParseError("The Outfitters product is missing its style number")
        product_name = self._canonical_product_name(title)
        options = self._option_positions(product.get("options"))
        variants = product.get("variants")
        if not isinstance(variants, list) or not variants:
            raise AdapterParseError("The Outfitters product contains no variants")

        listings: list[RetailerListing] = []
        for position, variant in enumerate(variants, start=1):
            if not isinstance(variant, Mapping):
                raise AdapterParseError(
                    f"The Outfitters variant {position} is not an object"
                )
            try:
                price = self._money(variant.get("price"), position, "price")
                compare_at = self._optional_money(variant.get("compare_at_price"))
                original_price = compare_at if compare_at and compare_at > price else None
                size = self._option_value(variant, options.get("size")) or "ONE SIZE"
                length = self._option_value(variant, options.get("length"))
                if length:
                    size = f"{size} / {length}"
                color = self._option_value(variant, options.get("color")) or "Unknown"
                sku = variant.get("sku")
                if not isinstance(sku, str) or not sku.strip():
                    variant_id = variant.get("id")
                    if variant_id is None:
                        raise AdapterParseError(
                            f"The Outfitters variant {position} is missing identity"
                        )
                    sku = f"shopify:{variant_id}"
                available = variant.get("available")
                stock_status = (
                    StockStatus.AVAILABLE
                    if available is True
                    else StockStatus.OUT_OF_STOCK
                    if available is False
                    else StockStatus.UNKNOWN
                )
                listings.append(
                    RetailerListing.model_validate(
                        {
                            "brand": "Arc'teryx",
                            "product_name": product_name,
                            "model_number": style_number,
                            "style_number": style_number,
                            "retailer": self.retailer_name,
                            "current_price": price,
                            "original_price": original_price,
                            "currency": "CAD",
                            "color": color,
                            "size": size,
                            "stock_status": stock_status,
                            "product_url": safe_url,
                            "image_url": self._variant_image(variant, product),
                            "variant_sku": sku,
                            "checked_at": checked_at,
                        }
                    )
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise AdapterParseError(
                    f"The Outfitters variant {position} is invalid: {error}"
                ) from error
        return listings

    @staticmethod
    def _option_positions(value: object) -> dict[str, int]:
        positions: dict[str, int] = {}
        if not isinstance(value, list):
            return positions
        for fallback_position, option in enumerate(value, start=1):
            name = option.get("name") if isinstance(option, Mapping) else option
            position = (
                option.get("position") if isinstance(option, Mapping) else fallback_position
            )
            if not isinstance(name, str) or not isinstance(position, int):
                continue
            key = normalize_lookup_key(name)
            if key.startswith("size"):
                positions["size"] = position
            elif key.startswith(("colour", "color")):
                positions["color"] = position
            elif key.startswith("length"):
                positions["length"] = position
        return positions

    @staticmethod
    def _option_value(variant: Mapping[str, Any], position: int | None) -> str | None:
        value = variant.get(f"option{position}") if position else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _money(value: object, position: int, label: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AdapterParseError(
                f"The Outfitters variant {position} is missing {label}"
            )
        try:
            return Decimal(str(value)) / Decimal("100")
        except (ArithmeticError, ValueError) as error:
            raise AdapterParseError(
                f"The Outfitters variant {position} has invalid {label}"
            ) from error

    @staticmethod
    def _optional_money(value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AdapterParseError("The Outfitters variant has invalid compare price")
        return Decimal(str(value)) / Decimal("100")

    @staticmethod
    def _variant_image(
        variant: Mapping[str, Any], product: Mapping[str, Any]
    ) -> str | None:
        image = variant.get("featured_image")
        if isinstance(image, Mapping):
            image = image.get("src")
        if not isinstance(image, str):
            image = product.get("featured_image")
        if isinstance(image, str) and image.startswith("//"):
            return f"https:{image}"
        return image if isinstance(image, str) and image.startswith("https://") else None

    @staticmethod
    def _style_from_text(value: str) -> str | None:
        match = re.search(r"\bX\d{9}\b", value, flags=re.IGNORECASE)
        return match.group(0).upper() if match else None

    @classmethod
    def _canonical_product_name(cls, title: str) -> str:
        value = re.sub(r"\s*-\s*X\d{9}.*$", "", title, flags=re.IGNORECASE)
        value = re.sub(r"\s*-\s*Past Season\s*$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\((Men|Women)(?:'s|s)\)", r"\1's", value)
        return f"Arc'teryx {value.strip()}"

    @staticmethod
    def _required_text(data: Mapping[str, Any], key: str, label: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AdapterParseError(f"The Outfitters data is missing {label}")
        return value.strip()
