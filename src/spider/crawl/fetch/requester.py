"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

import asyncio
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
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(cap)

    async def request_url(self, url: NormalizedUrl) -> FetchResult | FetchFailure | NotStarted:
        """A URL's own request, which the URL limit counts with the slots held, so the count is
        exact. After a stop, none starts (design D16)."""
        async with self._slots(url):
            # The start the gate gave it stays taken: after a refusal, no request starts.
            if self._stopped() or not self._limits.start_request():
                return NotStarted()
            return await self._send(url)

    async def request_robots_txt(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """One hop of an origin's robots.txt, which the URL limit never counts (design D6)."""
        async with self._slots(url):
            return await self._send(url)

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
