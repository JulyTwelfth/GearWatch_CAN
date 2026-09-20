"""Retailer-specific data adapters."""

from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.adapters.base import RetailerAdapter
from app.adapters.errors import AdapterParseError
from app.adapters.sporting_life import FixturePage, SportingLifeAdapter

__all__ = [
    "ArcTeryxOutletAdapter",
    "AdapterParseError",
    "FixturePage",
    "RetailerAdapter",
    "SportingLifeAdapter",
]
