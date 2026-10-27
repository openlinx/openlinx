"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from spider.clock import Clock
from spider.crawl.fetch.fetcher import Fetcher, FetchFailure, FetchResult, Request
from spider.crawl.fetch.politeness import RateGate, RequestLimits
from spider.crawl.urls import NormalizedUrl, host_key


def watchdog_seconds(request_deadline_seconds: float) -> float:
    """How long a request attempt may take before the watchdog ends it: a backstop behind the
    Fetcher's own deadline, which it never cuts (design D16)."""
    return max(120, request_deadline_seconds + 30)


# The rate of progress events counts the URL requests started this long ago or since.
RATE_WINDOW_SECONDS = 60


@dataclass(frozen=True, slots=True)
class NotStarted:
    """A stop or the URL limit kept a URL's request from starting, which leaves the URL
    queued."""


class Requester:
    """The host's slot, its turn under --rate, the global cap and the URL limit for every
    request; the watchdog, the network pause and 022's retries belong here, not in its callers."""

    def __init__(
        self,
        fetcher: Fetcher,
        limits: RequestLimits,
        gate: RateGate,
        *,
        concurrency: int,
        cap: int,
        clock: Clock,
        watchdog_seconds: float,
        stopped: Callable[[], bool],
    ) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._gate = gate
        self._concurrency = concurrency
        self._clock = clock
        self._watchdog_seconds = watchdog_seconds
        self._stopped = stopped
        self._starts: deque[float] = deque()
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(cap)
        # The network pause's gate: set while requests may start (design D16).
        self._open = asyncio.Event()
        self._open.set()

    def close_gate(self) -> None:
        self._open.clear()

    def open_gate(self) -> None:
        self._open.set()

    async def request_url(self, url: NormalizedUrl) -> FetchResult | FetchFailure | NotStarted:
        """A URL's own request, which the URL limit counts with the slots held, so the count is
        exact. After a stop, none starts (design D16)."""
        async with self._gated_slots(url):
            # Refused with its turn under --rate already taken, and never given back: after a
            # stop or at the limit, no request starts again.
            if self._stopped() or not self._limits.start_request():
                return NotStarted()
            self._starts.append(self._clock.monotonic())
            return await self._send(url)

    def give_back(self) -> None:
        """A URL request that is made again, as if it had not started (design D16)."""
        self._limits.give_back()
        if self._starts:
            self._starts.pop()

    def rate(self, elapsed: float) -> float:
        """URL requests started per second, over the window or the `elapsed` seconds the run
        has lasted when that is shorter."""
        oldest = self._clock.monotonic() - RATE_WINDOW_SECONDS
        while self._starts and self._starts[0] <= oldest:
            self._starts.popleft()
        seconds = min(RATE_WINDOW_SECONDS, elapsed)
        return round(len(self._starts) / seconds, 3) if seconds > 0 else 0.0

    async def request_robots_txt(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """One hop of an origin's robots.txt, which the URL limit never counts (design D6)."""
        async with self._gated_slots(url):
            return await self._send(url)

    async def request_probe(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """A probe of the network pause: through the host's slot, its turn and the global cap,
        but never the pause's gate or the URL limit (design D16)."""
        async with self._slots(url):
            return await self._send(url)

    @asynccontextmanager
    async def _gated_slots(self, url: NormalizedUrl) -> AsyncIterator[None]:
        # Waited before any slot, so a paused request leaves the host's slots to the probes; one
        # that took them as the pause began gives them back and its turn goes unused.
        while True:
            await self._open.wait()
            async with self._slots(url):
                if self._open.is_set():
                    yield
                    return

    @asynccontextmanager
    async def _slots(self, url: NormalizedUrl) -> AsyncIterator[None]:
        # The host's slot, then its turn under --rate, then the global cap: a request waiting
        # for a busy host, or for its turn, holds no global permit.
        host = host_key(url)
        async with self._host(host):
            await self._gate.wait_turn(host)
            async with self._requests:
                await self._gate.started(host)
                yield

    def _host(self, host: str) -> asyncio.Semaphore:
        semaphore = self._hosts.get(host)
        if semaphore is None:
            semaphore = self._hosts[host] = asyncio.Semaphore(self._concurrency)
        return semaphore

    async def _send(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        # Each attempt races its own watchdog on the Crawl's Clock, from when it started, which
        # its row keeps as the Fetcher's would.
        started_at = self._clock.now()
        fetch = asyncio.ensure_future(self._fetcher.fetch(Request(url)))
        watchdog = asyncio.ensure_future(self._clock.sleep(self._watchdog_seconds))
        try:
            await asyncio.wait((fetch, watchdog), return_when=asyncio.FIRST_COMPLETED)
        finally:
            fetch.cancel()
            watchdog.cancel()
            # Both have ended before the slots are given back.
            await asyncio.wait((fetch, watchdog))
        if not fetch.cancelled():
            return fetch.result()
        return FetchFailure(
            fetch_error="watchdog",
            message=f"No response within {self._watchdog_seconds:g} seconds",
            fetched_at=started_at,
        )
