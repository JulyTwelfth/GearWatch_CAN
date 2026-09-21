from app.adapters.arcteryx_outlet import ArcTeryxOutletAdapter
from app.commands.collect import build_configured_adapters, summary_payload
from app.core.config import Settings
from app.services.collection import AdapterFailure
from app.services.collection_run import CollectionRunSummary


def test_empty_url_setting_builds_no_live_adapters() -> None:
    settings = Settings(_env_file=None, arcteryx_outlet_product_urls="  ")

    assert build_configured_adapters(settings) == ()


def test_configured_urls_are_trimmed_and_deduplicated() -> None:
    first = "https://outlet.arcteryx.com/ca/en/shop/mens/fixture-one"
    second = "https://outlet.arcteryx.com/ca/en/shop/womens/fixture-two"
    settings = Settings(
        _env_file=None,
        arcteryx_outlet_product_urls=f" {first}, {second}, {first} ",
    )

    adapters = build_configured_adapters(settings)

    assert len(adapters) == 1
    assert isinstance(adapters[0], ArcTeryxOutletAdapter)
    assert settings.configured_arcteryx_outlet_urls() == (first, second)


def test_summary_payload_does_not_include_exception_messages() -> None:
    summary = CollectionRunSummary(
        configured_retailers=("Working", "Failed"),
        successful_retailers=("Working",),
        failures=(AdapterFailure(retailer="Failed", error_type="TimeoutError"),),
        listings_processed=3,
        price_snapshots_created=2,
        inventory_snapshots_created=1,
    )

    payload = summary_payload(summary)

    assert payload == {
        "status": "partial_failure",
        "configured_retailers": ["Working", "Failed"],
        "successful_retailers": ["Working"],
        "failures": [{"retailer": "Failed", "error_type": "TimeoutError"}],
        "listings_processed": 3,
        "price_snapshots_created": 2,
        "inventory_snapshots_created": 1,
        "fetch_statuses_created": 0,
    }


def test_summary_payload_identifies_failed_product_resource() -> None:
    resource = "https://outlet.arcteryx.com/ca/en/shop/mens/removed-product"
    summary = CollectionRunSummary(
        configured_retailers=("Arc'teryx Outlet Canada",),
        successful_retailers=("Arc'teryx Outlet Canada",),
        failures=(
            AdapterFailure(
                retailer="Arc'teryx Outlet Canada",
                error_type="HttpFetchError",
                resource=resource,
            ),
        ),
        listings_processed=3,
        price_snapshots_created=3,
        inventory_snapshots_created=3,
    )

    payload = summary_payload(summary)

    assert payload["status"] == "partial_failure"
    assert payload["failures"] == [
        {
            "retailer": "Arc'teryx Outlet Canada",
            "error_type": "HttpFetchError",
            "resource": resource,
        }
    ]
