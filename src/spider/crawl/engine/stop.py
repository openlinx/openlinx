"""The stop flag of a Crawl, set once with its stop_reason, and the grace of a stop
(020-add-crawl-core D10, D16)."""

import asyncio
from collections.abc import Callable

from spider.clock import Clock
from spider.store.failures import write_failure_cause
from spider.store.records import StopReason
from spider.store.transitions import TRANSITIONS


def _rank(reason: StopReason) -> int:
    if reason == "write_failed":
        return 2
    return 1 if reason in TRANSITIONS["running", "failed"] else 0


class StopSignal:
    def __init__(self) -> None:
        self._reason: StopReason | None = None
        self._cause: BaseException | None = None
        self._on_first_set: list[Callable[[StopReason], object]] = []
        self._was_set = asyncio.Event()
        self._closed = False

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
        """The first stop counts, but a failure outranks a stop and a write failure the
        network failures: a Crawl that stopped at its URL limit and then lost its file has
        failed (design D10, D16)."""
        if self._closed:
            return
        first = self._reason is None
        if self._reason is None or _rank(reason) > _rank(self._reason):
            self._reason, self._cause = reason, cause
        # Before the callbacks, so a waiter wakes even if one of them raises.
        self._was_set.set()
        if first:
            for callback in self._on_first_set:
                callback(reason)

    def write_failed(self, error: BaseException) -> None:
        """Writing the crawl file failed, wherever it was written."""
        self.set("write_failed", write_failure_cause(error))

    def close(self) -> StopReason | None:
        """The end's one read of the reason: a stop set after it, during the passes or the
        end's writes, changes nothing and writes no stopping event, since the Crawl ends as
        its empty frontier says (design D10)."""
        self._closed = True
        return self._reason

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
