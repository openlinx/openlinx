"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from spider.crawl.fetcher import Fetcher, FetchFailure, FetchResult, Request
from spider.crawl.politeness import RateGate, RequestLimits
from spider.crawl.urls import NormalizedUrl, url_host


@dataclass(frozen=True, slots=True)
class UrlLimitRefused:
    """The URL limit refused a URL's request, which leaves the URL queued."""


class Requester:
    """The host's slot, its turn under --rate, the global cap and the URL limit for every
    request; the watchdog, the network pause and 022's retries belong here, not in its callers."""

    def __init__(self, fetcher: Fetcher, limits: RequestLimits, gate: RateGate) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._gate = gate

    async def request_url(self, url: NormalizedUrl) -> FetchResult | FetchFailure | UrlLimitRefused:
        """A URL's own request, which the URL limit counts with the slots held, so the count is
        exact."""
        async with self._slots(url):
            if not self._limits.start_request():
                # The start the gate gave it stays taken: after a refusal, no request starts.
                return UrlLimitRefused()
            return await self._send(url)

    def refuses_a_new_request(self) -> bool:
        """Asked before a URL's robots.txt, which a URL the limit refuses never requests
        (design D6)."""
        return self._limits.refused()

    async def request_robots_txt(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """One hop of an origin's robots.txt, which the URL limit never counts (design D6)."""
        async with self._slots(url):
            return await self._send(url)

    @asynccontextmanager
    async def _slots(self, url: NormalizedUrl) -> AsyncIterator[None]:
        # The host's slot, then its turn under --rate, then the global cap: a request waiting
        # for a busy host, or for its turn, holds no global permit.
        host = url_host(url)
        async with self._limits.host(host):
            await self._gate.wait_turn(host)
            async with self._limits.request():
                await self._gate.started(host)
                yield

    async def _send(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        return await self._fetcher.fetch(Request(url))
