import json
import logging

from sqlalchemy.orm import Session, sessionmaker

from app.adapters import (
    ArcTeryxCanadaAdapter,
    ArcTeryxOutletAdapter,
    MonodSportsAdapter,
    RetailerAdapter,
    VpoAdapter,
)
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.services.collection_run import CollectionRunService, CollectionRunSummary

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIGURATION = 2


def build_configured_adapters(settings: Settings) -> tuple[RetailerAdapter, ...]:
    adapters: list[RetailerAdapter] = []
    configurations = (
        (ArcTeryxCanadaAdapter, settings.configured_arcteryx_canada_urls()),
        (ArcTeryxOutletAdapter, settings.configured_arcteryx_outlet_urls()),
        (MonodSportsAdapter, settings.configured_monod_sports_urls()),
        (VpoAdapter, settings.configured_vpo_urls()),
    )
    for adapter_type, urls in configurations:
        if urls:
            adapters.append(adapter_type(product_urls=urls))
    return tuple(adapters)


def summary_payload(summary: CollectionRunSummary) -> dict[str, object]:
    failures: list[dict[str, str]] = []
    for failure in summary.failures:
        item = {
            "retailer": failure.retailer,
            "error_type": failure.error_type,
        }
        if failure.resource is not None:
            item["resource"] = failure.resource
        failures.append(item)

    return {
        "status": summary.status,
        "configured_retailers": list(summary.configured_retailers),
        "successful_retailers": list(summary.successful_retailers),
        "failures": failures,
        "listings_processed": summary.listings_processed,
        "price_snapshots_created": summary.price_snapshots_created,
        "inventory_snapshots_created": summary.inventory_snapshots_created,
        "fetch_statuses_created": summary.fetch_statuses_created,
        "listing_variants_deactivated": summary.listing_variants_deactivated,
    }


def run_with_session_factory(
    adapters: tuple[RetailerAdapter, ...],
    session_factory: sessionmaker[Session],
) -> CollectionRunSummary:
    with session_factory.begin() as session:
        return CollectionRunService().run(adapters, session)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()

    try:
        adapters = build_configured_adapters(settings)
    except ValueError as error:
        print(
            json.dumps(
                {
                    "status": "configuration_error",
                    "error_type": type(error).__name__,
                }
            )
        )
        return EXIT_CONFIGURATION

    if not adapters:
        print(
            json.dumps(
                {
                    "status": "configuration_error",
                    "error_type": "MissingProductUrls",
                }
            )
        )
        return EXIT_CONFIGURATION

    engine = create_db_engine(settings.database_url)
    try:
        summary = run_with_session_factory(adapters, create_session_factory(engine))
    except Exception as error:
        logger.error(
            "Collection transaction failed",
            extra={"error_type": type(error).__name__},
        )
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        return EXIT_FAILURE
    finally:
        engine.dispose()

    print(json.dumps(summary_payload(summary)))
    if summary.status == "failed":
        return EXIT_FAILURE
    if summary.status == "partial_failure":
        return EXIT_CONFIGURATION
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
