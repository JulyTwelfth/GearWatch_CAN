from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from app.adapters.base import RetailerAdapter
from app.adapters.errors import AdapterParseError
from app.schemas.retailer import RetailerListing


@dataclass(frozen=True, slots=True)
class FixturePage:
    """Local-only HTML source used while live collection is disabled."""

    html: str
    product_url: str
    checked_at: datetime


class SportingLifeAdapter(RetailerAdapter):
    """Parse sanitized fixture pages without making network requests."""

    retailer_name = "Sporting Life"

    def __init__(self, pages: Sequence[FixturePage] = ()) -> None:
        self._pages = tuple(pages)

    def collect(self) -> Sequence[RetailerListing]:
        listings: list[RetailerListing] = []
        for page in self._pages:
            listings.extend(
                self.parse_product_page(
                    page.html,
                    product_url=page.product_url,
                    checked_at=page.checked_at,
                )
            )
        return listings

    def parse_product_page(
        self,
        html: str,
        *,
        product_url: str,
        checked_at: datetime,
    ) -> list[RetailerListing]:
        soup = BeautifulSoup(html, "html.parser")
        product = soup.select_one("[data-product-detail]")
        if not isinstance(product, Tag):
            raise AdapterParseError("Sporting Life fixture is missing the product detail root")

        brand = self._required_attribute(product, "data-brand", "brand")
        model_number = product.get("data-model-number")
        currency = product.get("data-currency", "CAD")
        product_name = self._required_text(product, "[data-product-name]", "product name")
        current_price = self._required_value(
            product, "[data-current-price]", "current price"
        )
        original_price = self._optional_value(product, "[data-original-price]")

        variants = product.select("[data-variant]")
        if not variants:
            raise AdapterParseError("Sporting Life fixture contains no product variants")

        listings: list[RetailerListing] = []
        for position, variant in enumerate(variants, start=1):
            try:
                listings.append(
                    RetailerListing.model_validate(
                        {
                            "brand": brand,
                            "product_name": product_name,
                            "model_number": model_number,
                            "retailer": self.retailer_name,
                            "current_price": current_price,
                            "original_price": original_price,
                            "currency": currency,
                            "color": self._required_attribute(
                                variant, "data-color", f"variant {position} color"
                            ),
                            "size": self._required_attribute(
                                variant, "data-size", f"variant {position} size"
                            ),
                            "stock_status": variant.get("data-stock-status"),
                            "product_url": product_url,
                            "checked_at": checked_at,
                        }
                    )
                )
            except (ValidationError, ValueError) as error:
                raise AdapterParseError(
                    f"Sporting Life fixture variant {position} is invalid: {error}"
                ) from error
        return listings

    @staticmethod
    def _required_attribute(element: Tag, attribute: str, label: str) -> str:
        value = element.get(attribute)
        if not isinstance(value, str) or not value.strip():
            raise AdapterParseError(f"Sporting Life fixture is missing {label}")
        return value

    @staticmethod
    def _required_text(product: Tag, selector: str, label: str) -> str:
        element = product.select_one(selector)
        if not isinstance(element, Tag):
            raise AdapterParseError(f"Sporting Life fixture is missing {label}")
        value = element.get_text(" ", strip=True)
        if not value:
            raise AdapterParseError(f"Sporting Life fixture has an empty {label}")
        return value

    @staticmethod
    def _required_value(product: Tag, selector: str, label: str) -> str:
        value = SportingLifeAdapter._optional_value(product, selector)
        if value is None:
            raise AdapterParseError(f"Sporting Life fixture is missing {label}")
        return value

    @staticmethod
    def _optional_value(product: Tag, selector: str) -> str | None:
        element = product.select_one(selector)
        if not isinstance(element, Tag):
            return None
        for attribute in ("content", "data-value"):
            value = element.get(attribute)
            if isinstance(value, str) and value.strip():
                return value
        text = element.get_text(" ", strip=True)
        return text or None

