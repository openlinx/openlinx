"""Measure capability for admitted origins independently of the URL tasks."""

import asyncio
from collections.abc import Awaitable, Callable

from openlinx.aio import first_of
from openlinx.clock import Clock
from openlinx.crawl.fetch.fetcher import FetchPolicy
from openlinx.crawl.fetch.requester import Requester
from openlinx.crawl.urls import NormalizedUrl, url_origin
from openlinx.store.origins import claim_http_version, next_http_version_claim, record_http_version
from openlinx.store.records import HttpVersion
from openlinx.store.writer import CrawlWriter


class HttpVersions:
    def __init__(
        self,
        writer: CrawlWriter,
        policy: FetchPolicy,
        clock: Clock,
        measure: Callable[[str], Awaitable[HttpVersion | None]] | None,
    ) -> None:
        self._writer = writer
        self._policy = policy
        self._clock = clock
        self._measure = measure
        self._ready = asyncio.Event()
        self._finishing = False

    async def requested(self, url: NormalizedUrl) -> None:
        origin = url_origin(url)
        if url.startswith("http://"):
            await self._writer.run_async(record_http_version(origin, "http_1_1"))
        elif self._measure is not None:
            deadline = self._clock.monotonic() + self._policy.timeout_seconds
            if await self._writer.run_async(claim_http_version(origin, deadline)):
                # A request holds its own slots here, so it only signals work in the store.
                self._ready.set()

    def finish(self) -> None:
        self._finishing = True
        self._ready.set()

    async def run(self, requester: Requester) -> None:
        measure = self._measure
        if measure is None:
            raise RuntimeError("A capability worker needs a Fetcher with an ALPN probe")
        writer, after = self._writer, 0
        while True:
            await self._ready.wait()
            self._ready.clear()
            while (pending := await writer.run_async(next_http_version_claim(after))) is not None:
                after, origin, deadline = pending
                left = deadline - self._clock.monotonic()
                if left <= 0:
                    continue
                measured = await first_of(
                    requester.measure_http_version(origin, measure), self._clock.sleep(left)
                )
                if measured.cancelled():
                    continue
                version = measured.result()
                if version is not None:
                    await writer.run_async(record_http_version(origin, version))
            if self._finishing and not self._ready.is_set():
                return
