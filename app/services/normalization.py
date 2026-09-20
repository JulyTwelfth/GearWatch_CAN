import re
import unicodedata
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class StockStatus(StrEnum):
    AVAILABLE = "Available"
    OUT_OF_STOCK = "Out of Stock"
    UNKNOWN = "Unknown"


_MODEL_LABEL_PATTERN = re.compile(
    r"\b(?:model|style|item|sku)\s*(?:number|no\.?)?\s*(?:#|:|-)?\s*"
    r"(?P<model>[a-z0-9][a-z0-9._-]{2,})",
    flags=re.IGNORECASE,
)
_ARCTERYX_MODEL_PATTERN = re.compile(r"\bX\d{9}\b", flags=re.IGNORECASE)


def normalize_text(value: str) -> str:
    """Normalize Unicode punctuation and repeated whitespace."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("’", "'").replace("‘", "'")
    return " ".join(normalized.split()).strip()


def normalize_lookup_key(value: str) -> str:
    """Build the punctuation-insensitive key used by persisted searchable fields."""
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value).casefold())


def normalize_brand(value: str) -> str:
    normalized = normalize_text(value)
    identity = re.sub(r"[^a-z0-9]", "", normalized.casefold())
    if identity == "arcteryx":
        return "Arc'teryx"
    return normalized


def normalize_product_name(value: str) -> str:
    normalized = normalize_text(value)
    return re.sub(
        r"\barc\s*'?\s*teryx\b",
        "Arc'teryx",
        normalized,
        flags=re.IGNORECASE,
    )


def extract_model_number(value: str | None) -> str | None:
    if not value:
        return None

    normalized = normalize_text(value)
    labelled_match = _MODEL_LABEL_PATTERN.search(normalized)
    if labelled_match:
        return normalize_model_number(labelled_match.group("model"))

    arcteryx_match = _ARCTERYX_MODEL_PATTERN.search(normalized)
    if arcteryx_match:
        return arcteryx_match.group(0).upper()
    return None


def normalize_model_number(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = normalize_text(value)
    extracted = _MODEL_LABEL_PATTERN.search(normalized)
    if extracted:
        normalized = extracted.group("model")

    normalized = re.sub(r"\s+", "", normalized).upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{2,}", normalized):
        raise ValueError("model number must contain at least three letters or digits")
    return normalized


def normalize_color(value: str) -> str:
    normalized = normalize_text(value)
    if not normalized:
        raise ValueError("color cannot be empty")

    aliases = {
        "bk": "Black",
        "blk": "Black",
        "black": "Black",
        "black sapphire": "Black Sapphire",
        "24k black": "24K Black",
    }
    key = normalized.casefold()
    if key in aliases:
        return aliases[key]

    if normalized.islower() or normalized.isupper():
        normalized = normalized.title()
    return re.sub(r"\b24k\b", "24K", normalized, flags=re.IGNORECASE)


def normalize_size(value: str) -> str:
    normalized = normalize_text(value)
    if not normalized:
        raise ValueError("size cannot be empty")

    key = re.sub(r"[\s_-]+", " ", normalized.casefold()).strip()
    aliases = {
        "extra extra small": "XXS",
        "xx small": "XXS",
        "xxs": "XXS",
        "extra small": "XS",
        "x small": "XS",
        "xs": "XS",
        "small": "S",
        "s": "S",
        "medium": "M",
        "med": "M",
        "m": "M",
        "large": "L",
        "l": "L",
        "extra large": "XL",
        "x large": "XL",
        "xl": "XL",
        "extra extra large": "XXL",
        "xx large": "XXL",
        "xxl": "XXL",
        "one size": "ONE SIZE",
        "one size fits all": "ONE SIZE",
        "os": "ONE SIZE",
        "osfa": "ONE SIZE",
    }
    if key in aliases:
        return aliases[key]

    compact = re.sub(r"\s*/\s*", "/", normalized).upper()
    if re.fullmatch(r"\d+\.0", compact):
        return compact[:-2]
    return compact


def normalize_stock_status(value: str | bool | int | None) -> StockStatus:
    if value is None:
        return StockStatus.UNKNOWN
    if isinstance(value, bool):
        return StockStatus.AVAILABLE if value else StockStatus.OUT_OF_STOCK
    if isinstance(value, int):
        return StockStatus.AVAILABLE if value > 0 else StockStatus.OUT_OF_STOCK

    normalized = normalize_text(value).casefold()
    if not normalized or normalized in {"unknown", "n/a", "not specified"}:
        return StockStatus.UNKNOWN

    out_of_stock_values = {
        "false",
        "no",
        "not available",
        "out of stock",
        "sold out",
        "unavailable",
    }
    available_values = {
        "available",
        "available online",
        "in stock",
        "low stock",
        "true",
        "yes",
    }
    if normalized in out_of_stock_values:
        return StockStatus.OUT_OF_STOCK
    if normalized in available_values or re.fullmatch(r"only \d+ left", normalized):
        return StockStatus.AVAILABLE
    return StockStatus.UNKNOWN


def parse_price(value: str | Decimal | int | float) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("price cannot be a boolean")

    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, (int, float)):
        amount = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = normalize_text(value).replace(" ", "")
        cleaned = re.sub(r"(?i)CAD", "", cleaned)
        cleaned = re.sub(r"(?i)C\$", "", cleaned).replace("$", "")
        if not re.fullmatch(r"-?\d[\d,.]*", cleaned):
            raise ValueError(f"cannot parse price: {value!r}")

        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            decimal_digits = len(cleaned) - cleaned.rfind(",") - 1
            cleaned = cleaned.replace(",", ".") if decimal_digits == 2 else cleaned.replace(",", "")

        try:
            amount = Decimal(cleaned)
        except InvalidOperation as error:
            raise ValueError(f"cannot parse price: {value!r}") from error
    else:
        raise TypeError("price must be text or a number")

    if not amount.is_finite() or amount < 0:
        raise ValueError("price must be a finite, non-negative amount")
    if amount.as_tuple().exponent < -2:
        raise ValueError("price cannot have more than two decimal places")
    return amount.quantize(Decimal("0.01"))


def calculate_discount(current_price: Decimal, original_price: Decimal | None) -> Decimal:
    current = parse_price(current_price)
    if original_price is None:
        return Decimal("0.00")

    original = parse_price(original_price)
    if original == 0:
        raise ValueError("original price must be greater than zero")
    if current >= original:
        return Decimal("0.00")

    discount = ((original - current) / original) * Decimal("100")
    return discount.quantize(Decimal("0.01"))
