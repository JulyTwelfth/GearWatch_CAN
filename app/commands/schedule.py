import json
import logging
import signal
from collections.abc import Callable
from threading import Event
from types import FrameType

from app.commands.collect import (
    EXIT_CONFIGURATION,
    EXIT_SUCCESS,
    build_configured_adapters,
)
from app.commands.collect import main as collect_once
from app.core.config import Settings, get_settings
from app.services.scheduler import CollectionScheduler, SchedulerSummary, StopSignal

logger = logging.getLogger(__name__)


def _configuration_error(error_type: str) -> int:
    print(json.dumps({"status": "configuration_error", "error_type": error_type}))
    return EXIT_CONFIGURATION


def run_scheduler(
    settings: Settings,
    *,
    cycle_runner: Callable[[], int] = collect_once,
    stop_signal: StopSignal,
) -> int:
    try:
        adapters = build_configured_adapters(settings)
    except ValueError as error:
        return _configuration_error(type(error).__name__)
    if not adapters:
        return _configuration_error("MissingProductUrls")

    logger.info(
        "Collection scheduler started",
        extra={
            "interval_seconds": settings.collection_interval_seconds,
            "run_on_startup": settings.collection_run_on_startup,
            "configured_retailers": [adapter.retailer_name for adapter in adapters],
        },
    )
    summary = CollectionScheduler(
        cycle_runner=cycle_runner,
        stop_signal=stop_signal,
        interval_seconds=settings.collection_interval_seconds,
        run_on_startup=settings.collection_run_on_startup,
    ).run()
    print(json.dumps(_shutdown_payload(summary)))
    return EXIT_SUCCESS


def _shutdown_payload(summary: SchedulerSummary) -> dict[str, object]:
    return {
        "status": "scheduler_stopped",
        "cycles_completed": summary.cycles_completed,
        "successful_cycles": summary.successful_cycles,
        "failed_cycles": summary.failed_cycles,
    }


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info(
            "Collection scheduler stop requested",
            extra={"signal": signal.Signals(signum).name},
        )
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop_event = Event()
    _install_signal_handlers(stop_event)
    return run_scheduler(get_settings(), stop_signal=stop_event)


if __name__ == "__main__":
    raise SystemExit(main())
