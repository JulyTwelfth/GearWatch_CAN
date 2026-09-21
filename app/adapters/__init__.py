"""Retailer-specific data adapters."""

from app.adapters.arcteryx_canada import ArcTeryxCanadaAdapter
from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.adapters.base import RetailerAdapter
from app.adapters.errors import AdapterParseError
from app.adapters.monod_sports import MonodSportsAdapter
from app.adapters.sporting_life import FixturePage, SportingLifeAdapter
from app.adapters.vpo import VpoAdapter

__all__ = [
    "ArcTeryxCanadaAdapter",
    "ArcTeryxOutletAdapter",
    "AdapterParseError",
    "FixturePage",
    "MonodSportsAdapter",
    "RetailerAdapter",
    "SportingLifeAdapter",
    "VpoAdapter",
]
