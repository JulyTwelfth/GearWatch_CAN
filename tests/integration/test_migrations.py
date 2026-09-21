import pytest
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.integration


def test_initial_migration_creates_required_tables(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)

    assert {
        "products",
        "retailers",
        "listings",
        "product_variants",
        "price_snapshots",
        "inventory_snapshots",
        "listing_variants",
        "fetch_statuses",
    }.issubset(set(inspector.get_table_names()))

    price_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("price_snapshots")
    }
    inventory_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("inventory_snapshots")
    }
    assert "uq_price_snapshots_point" in price_constraints
    assert "uq_inventory_snapshots_point" in inventory_constraints
    listing_variant_columns = {
        column["name"] for column in inspector.get_columns("listing_variants")
    }
    assert {"is_active", "last_seen_at"}.issubset(listing_variant_columns)
