"""`FakeClock`, the virtual clock of the timing tests (design D8 of 000-scaffold-project,
D7 of 020-add-crawl-core)."""

import asyncio
import heapq
import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

# Yields of the loop in a row with no clock call between them, after which nothing else can
# run: each yield lets every callback that was ready run once.
_QUIET_YIELDS = 20


class FakeClock:
    """Each sleep wakes at its own time. Time jumps to the earliest wake once nothing else can
    run on the loop and nothing the loop waits for runs off it, as trio's
    MockClock(autojump_threshold=0) does; advance() moves it by hand, for tests without a loop."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=UTC) if start is None else start
        self._monotonic = 0.0
        self._sleepers: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self._calls = 0
        self._holds = 0
        self._released: asyncio.Event | None = None
        self._jumper: asyncio.Task[None] | None = None

    def now(self) -> datetime:
        self._calls += 1
        return self._now

    def monotonic(self) -> float:
        self._calls += 1
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds
        self._wake_due()

    async def sleep(self, seconds: float) -> None:
        self._calls += 1
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        woken: asyncio.Future[None] = loop.create_future()
        heapq.heappush(self._sleepers, (self._monotonic + seconds, next(self._order), woken))
        if self._jumper is None or self._jumper.done():
            self._jumper = loop.create_task(self._jump())
        await woken

    @contextmanager
    def off_loop(self) -> Iterator[None]:
        self._calls += 1
        self._holds += 1
        try:
            yield
        finally:
            self._holds -= 1
            self._calls += 1
            if self._holds == 0 and self._released is not None:
                self._released.set()

    async def _jump(self) -> None:
        while self._live_sleepers():
            await self._settled()
            if not self._live_sleepers():
                return
            wake = self._sleepers[0][0]
            self.advance(wake - self._monotonic)

    async def _settled(self) -> None:
        """Returns once nothing else runs: no clock call in _QUIET_YIELDS yields in a row, and
        no hold open."""
        quiet = 0
        while quiet < _QUIET_YIELDS:
            if self._holds:
                self._released = asyncio.Event()
                await self._released.wait()
                quiet = 0
                continue
            calls = self._calls
            await asyncio.sleep(0)
            quiet = quiet + 1 if calls == self._calls and not self._holds else 0

    def _live_sleepers(self) -> bool:
        while self._sleepers and self._sleepers[0][2].done():
            heapq.heappop(self._sleepers)
        return bool(self._sleepers)

    def _wake_due(self) -> None:
        while self._sleepers and self._sleepers[0][0] <= self._monotonic:
            _, _, woken = heapq.heappop(self._sleepers)
            if not woken.done():
                woken.set_result(None)
