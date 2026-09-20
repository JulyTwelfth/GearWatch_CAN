from decimal import Decimal

import pytest

from app.services.normalization import (
    StockStatus,
    calculate_discount,
    extract_model_number,
    normalize_brand,
    normalize_color,
    normalize_lookup_key,
    normalize_size,
    normalize_stock_status,
    parse_price,
)


def test_normalize_lookup_key_matches_persisted_search_identity() -> None:
    assert normalize_lookup_key(" Arc'teryx / Beta Jacket ") == "arcteryxbetajacket"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$499.95", Decimal("499.95")),
        ("CAD $1,100.00", Decimal("1100.00")),
        ("1 099,95 $", Decimal("1099.95")),
        ("C$ 360", Decimal("360.00")),
        (Decimal("80"), Decimal("80.00")),
    ],
)
def test_parse_price_accepts_canadian_retail_formats(
    raw: str | Decimal, expected: Decimal
) -> None:
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw", ["free", "$12.345", "-$10.00", "NaN"])
def test_parse_price_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_price(raw)


@pytest.mark.parametrize(
    ("current", "original", "expected"),
    [
        (Decimal("75"), Decimal("100"), Decimal("25.00")),
        (Decimal("99.99"), Decimal("120"), Decimal("16.68")),
        (Decimal("100"), Decimal("100"), Decimal("0.00")),
        (Decimal("100"), None, Decimal("0.00")),
    ],
)
def test_calculate_discount(
    current: Decimal, original: Decimal | None, expected: Decimal
) -> None:
    assert calculate_discount(current, original) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("x-small", "XS"),
        (" Medium ", "M"),
        ("extra large", "XL"),
        ("one size fits all", "ONE SIZE"),
        ("s / m", "S/M"),
        ("10.0", "10"),
    ],
)
def test_normalize_size(raw: str, expected: str) -> None:
    assert normalize_size(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" blk ", "Black"),
        ("BLACK SAPPHIRE", "Black Sapphire"),
        ("24k black", "24K Black"),
        ("dynasty", "Dynasty"),
    ],
)
def test_normalize_color(raw: str, expected: str) -> None:
    assert normalize_color(raw) == expected


@pytest.mark.parametrize("raw", ["Arc’teryx", "ARC TERYX", "arcteryx", "Arc'teryx"])
def test_normalize_brand(raw: str) -> None:
    assert normalize_brand(raw) == "Arc'teryx"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Model: X000009856", "X000009856"),
        ("Style No. 29686", "29686"),
        ("Item #: x000007584", "X000007584"),
        ("Arc'teryx Beta Jacket X000009859", "X000009859"),
        ("Beta Jacket 2026", None),
    ],
)
def test_extract_model_number(raw: str, expected: str | None) -> None:
    assert extract_model_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("In Stock", StockStatus.AVAILABLE),
        ("Only 2 left", StockStatus.AVAILABLE),
        (True, StockStatus.AVAILABLE),
        ("Sold Out", StockStatus.OUT_OF_STOCK),
        (False, StockStatus.OUT_OF_STOCK),
        ("Pre-order", StockStatus.UNKNOWN),
        (None, StockStatus.UNKNOWN),
    ],
)
def test_normalize_stock_status(
    raw: str | bool | None, expected: StockStatus
) -> None:
    assert normalize_stock_status(raw) is expected
