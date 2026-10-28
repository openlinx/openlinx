"""The stop flag of a Crawl: set once, with its stop_reason (020-add-crawl-core D10)."""

import asyncio
from collections.abc import Callable

from spider.store.records import StopReason
from spider.store.transitions import TRANSITIONS

_FAILURES = TRANSITIONS["running", "failed"]


class StopSignal:
    def __init__(self) -> None:
        self._reason: StopReason | None = None
        self._cause: BaseException | None = None
        self._on_first_set: Callable[[StopReason], object] | None = None
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
        """`callback` gets the first reason set, which writes the stopping event."""
        self._on_first_set = callback

    def set(self, reason: StopReason, cause: BaseException | None = None) -> None:
        """The first stop counts, but a failure outranks a stop: a Crawl that stopped at its
        URL limit and then lost its file has failed (design D10)."""
        first = self._reason is None
        if first or (reason in _FAILURES and self._reason not in _FAILURES):
            self._reason, self._cause = reason, cause
        if first and self._on_first_set is not None:
            self._on_first_set(reason)
        self._was_set.set()

    async def wait(self) -> None:
        await self._was_set.wait()
