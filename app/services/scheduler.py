import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

CycleRunner = Callable[[], int]


class StopSignal(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class SchedulerSummary:
    cycles_completed: int
    successful_cycles: int
    failed_cycles: int


class CollectionScheduler:
    """Run isolated collection cycles until a cooperative stop signal is set."""

    def __init__(
        self,
        *,
        cycle_runner: CycleRunner,
        stop_signal: StopSignal,
        interval_seconds: int,
        run_on_startup: bool = True,
    ) -> None:
        self._cycle_runner = cycle_runner
        self._stop_signal = stop_signal
        self._interval_seconds = interval_seconds
        self._run_on_startup = run_on_startup

    def run(self) -> SchedulerSummary:
        cycles_completed = 0
        successful_cycles = 0
        failed_cycles = 0

        if not self._run_on_startup and self._stop_signal.wait(
            self._interval_seconds
        ):
            return SchedulerSummary(0, 0, 0)

        while not self._stop_signal.is_set():
            try:
                exit_code = self._cycle_runner()
            except Exception as error:
                logger.error(
                    "Scheduled collection cycle raised an unexpected error",
                    extra={"error_type": type(error).__name__},
                )
                exit_code = 1

            cycles_completed += 1
            if exit_code == 0:
                successful_cycles += 1
            else:
                failed_cycles += 1

            logger.info(
                "Scheduled collection cycle completed",
                extra={
                    "cycle_number": cycles_completed,
                    "exit_code": exit_code,
                    "next_run_seconds": self._interval_seconds,
                },
            )
            if self._stop_signal.wait(self._interval_seconds):
                break

        return SchedulerSummary(
            cycles_completed=cycles_completed,
            successful_cycles=successful_cycles,
            failed_cycles=failed_cycles,
        )
