import pytest

from app.services.scheduler import CollectionScheduler


class StopAfterWaits:
    def __init__(self, waits_before_stop: int) -> None:
        self.waits_before_stop = waits_before_stop
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return len(self.waits) >= self.waits_before_stop

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        return self.is_set()


def test_scheduler_runs_immediately_and_continues_after_failed_cycles() -> None:
    exit_codes = iter((0, 2, 1))
    stop_signal = StopAfterWaits(waits_before_stop=3)

    summary = CollectionScheduler(
        cycle_runner=lambda: next(exit_codes),
        stop_signal=stop_signal,
        interval_seconds=300,
    ).run()

    assert summary.cycles_completed == 3
    assert summary.successful_cycles == 1
    assert summary.failed_cycles == 2
    assert stop_signal.waits == [300, 300, 300]


def test_scheduler_can_wait_before_first_cycle() -> None:
    cycle_calls = 0
    stop_signal = StopAfterWaits(waits_before_stop=1)

    def cycle() -> int:
        nonlocal cycle_calls
        cycle_calls += 1
        return 0

    summary = CollectionScheduler(
        cycle_runner=cycle,
        stop_signal=stop_signal,
        interval_seconds=600,
        run_on_startup=False,
    ).run()

    assert summary.cycles_completed == 0
    assert cycle_calls == 0
    assert stop_signal.waits == [600]


def test_scheduler_isolates_unexpected_cycle_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop_signal = StopAfterWaits(waits_before_stop=1)

    def failed_cycle() -> int:
        raise RuntimeError("synthetic secret that must not be logged")

    summary = CollectionScheduler(
        cycle_runner=failed_cycle,
        stop_signal=stop_signal,
        interval_seconds=300,
    ).run()

    assert summary.cycles_completed == 1
    assert summary.successful_cycles == 0
    assert summary.failed_cycles == 1
    assert "synthetic secret" not in caplog.text
