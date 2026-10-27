"""Every unit's outcome, and the fallback of a URL whose unit failed (020-add-crawl-core D2)."""

import asyncio
from contextlib import suppress
from typing import Any

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import record_failure
from spider.crawl.engine.hooks import UrlResult
from spider.store.failures import is_one_urls_failure
from spider.store.records import Provenance
from spider.store.urls import UrlUnit, record_unwritten
from spider.store.writer import CrawlWriterClosedError


class Outcomes:
    """Every submitted unit's Future until its outcome has reached the engine (design D2)."""

    def __init__(self, context: CrawlContext) -> None:
        self._context = context
        self._pending: set[asyncio.Future[Any]] = set()

    async def submit(self, result: UrlResult, unit: UrlUnit) -> None:
        future = await self._context.writer.submit_async(unit)
        self._pending.add(future)
        future.add_done_callback(lambda done: self._unit_done(result, done))

    async def settled(self) -> None:
        """Waits for every outcome, fallback units included."""
        while self._pending:
            # The writer commits on its own only every 500 units or second of clock time.
            with suppress(CrawlWriterClosedError):
                # An ended writer has already failed every Future it held.
                await asyncio.to_thread(self._context.writer.flush)
            # Outcomes that the flush resolved have already left the set.
            if self._pending:
                await asyncio.wait(set(self._pending))

    def _unit_done(self, result: UrlResult, done: asyncio.Future[None]) -> None:
        self._pending.discard(done)
        error = done.exception()
        if error is None:
            return
        if not is_one_urls_failure(error):
            self._context.stop.set("write_failed", error)
            return
        self._context.reporter.count(record_failure(result.url, error), result.url)
        fallback = asyncio.ensure_future(self._fall_back(result, error))
        self._pending.add(fallback)
        fallback.add_done_callback(self._pending.discard)

    async def _fall_back(self, result: UrlResult, error: BaseException) -> None:
        message = f"{type(error).__name__}: {error}"
        unit = record_unwritten(
            result.url_id,
            message,
            blocked_by_robots_txt=result.blocked_by_robots_txt,
            provenance=provenance_of(result),
        )
        try:
            await (await self._context.writer.submit_async(unit))
        # A fallback that fails is the file's failure, not the URL's (design D2).
        except Exception as failure:
            self._context.stop.set("write_failed", failure)


def provenance_of(result: UrlResult) -> Provenance:
    return Provenance(
        crawl_depth=result.crawl_depth,
        discovered_via=result.discovered_via,
        found_on_url_id=result.found_on_url_id,
    )
