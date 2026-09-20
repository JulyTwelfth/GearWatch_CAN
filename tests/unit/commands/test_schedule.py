import json

import pytest

from app.commands.schedule import run_scheduler
from app.core.config import Settings


class StopAfterOneCycle:
    def __init__(self) -> None:
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, _timeout: float) -> bool:
        self.stopped = True
        return True


def test_scheduler_command_rejects_missing_product_urls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(_env_file=None, arcteryx_outlet_product_urls="")

    exit_code = run_scheduler(settings, stop_signal=StopAfterOneCycle())

    assert exit_code == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "configuration_error",
        "error_type": "MissingProductUrls",
    }


def test_scheduler_command_reports_graceful_shutdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        _env_file=None,
        arcteryx_outlet_product_urls=(
            "https://outlet.arcteryx.com/ca/en/shop/mens/fixture-scheduler-shell"
        ),
        collection_interval_seconds=300,
    )

    exit_code = run_scheduler(
        settings,
        cycle_runner=lambda: 0,
        stop_signal=StopAfterOneCycle(),
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "scheduler_stopped",
        "cycles_completed": 1,
        "successful_cycles": 1,
        "failed_cycles": 0,
    }
