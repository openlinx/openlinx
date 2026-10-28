"""The stop flag of a Crawl, set once with its stop_reason, and the grace of a stop
(020-add-crawl-core D10, D16)."""

import asyncio
from collections.abc import Callable

from spider.clock import Clock
from spider.store.records import StopReason
from spider.store.transitions import TRANSITIONS

_FAILURES = TRANSITIONS["running", "failed"]


class StopSignal:
    def __init__(self) -> None:
        self._reason: StopReason | None = None
        self._cause: BaseException | None = None
        self._on_first_set: list[Callable[[StopReason], object]] = []
        self._was_set = asyncio.Event()

    @property
    def is_set(self) -> bool:
        return self._reason is not None

    @property
    def reason(self) -> StopReason | None:
        return self._reason

    @property
    def cause(self) -> BaseException | None:
        """The error that ended the Crawl, with write_failed; None for the other reasons."""
        return self._cause

    def on_first_set(self, callback: Callable[[StopReason], object]) -> None:
        """`callback` gets the first reason set, as the stopping event and the grace need."""
        self._on_first_set.append(callback)

    def set(self, reason: StopReason, cause: BaseException | None = None) -> None:
        """The first stop counts, but a failure outranks a stop: a Crawl that stopped at its
        URL limit and then lost its file has failed (design D10)."""
        first = self._reason is None
        if first or (reason in _FAILURES and self._reason not in _FAILURES):
            self._reason, self._cause = reason, cause
        # Before the callbacks, so a waiter wakes even if one of them raises.
        self._was_set.set()
        if first:
            for callback in self._on_first_set:
                callback(reason)

    async def wait(self) -> None:
        await self._was_set.wait()


class StopGrace:
    """The grace of a stop: the requests in flight then get these seconds of clock time in all,
    the depth's and the Checked URLs' alike, from the stop (design D16)."""

    def __init__(self, clock: Clock, seconds: float) -> None:
        self._clock = clock
        self._seconds = seconds
        self._ends: float | None = None

    def start(self) -> float:
        """When the grace ends, set at the first call."""
        if self._ends is None:
            self._ends = self._clock.monotonic() + self._seconds
        return self._ends

    def remaining(self) -> float:
        """Starts it, for a stop set before the run could start it."""
        return max(0.0, self.start() - self._clock.monotonic())
