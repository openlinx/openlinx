"""Every unit's outcome, and the fallback of a URL whose unit failed (020-add-crawl-core D2)."""

import asyncio
from contextlib import suppress
from typing import Any

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.hooks import UrlResult
from spider.output.codes import RECORD_FAILED
from spider.output.diagnostics import Diagnostic
from spider.store.failures import is_one_urls_failure
from spider.store.urls import UrlUnit, record_unwritten
from spider.store.writer import CrawlWriterClosedError


class Outcomes:
    """Every submitted unit's Future until its outcome has reached the engine (design D2)."""

    def __init__(self, context: CrawlContext) -> None:
        self._context = context
        self._pending: set[asyncio.Future[Any]] = set()
        self._pending_urls: set[int] = set()

    def is_pending(self, url_id: int) -> bool:
        """True from the submit of the URL's unit until its outcome, a fallback's included."""
        return url_id in self._pending_urls

    async def submit(self, result: UrlResult, unit: UrlUnit) -> None:
        future = await self._context.writer.submit_async(unit)
        self._pending.add(future)
        self._pending_urls.add(result.url_id)
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
        if error is None or not is_one_urls_failure(error):
            self._pending_urls.discard(result.url_id)
            if error is not None:
                self._context.stop.set("write_failed", error)
            return
        self._context.reporter.count(
            Diagnostic.of(
                RECORD_FAILED,
                f"Recording {result.url} failed ({type(error).__name__}), so it was recorded "
                "as an error, without the URLs found on it and its handlers' rows.",
            ),
            result.url,
        )
        fallback = asyncio.ensure_future(self._fall_back(result, error))
        self._pending.add(fallback)
        fallback.add_done_callback(self._pending.discard)
        fallback.add_done_callback(lambda _: self._pending_urls.discard(result.url_id))

    async def _fall_back(self, result: UrlResult, error: BaseException) -> None:
        message = f"{type(error).__name__}: {error}"
        unit = record_unwritten(
            result.url_id,
            message,
            blocked_by_robots_txt=result.blocked_by_robots_txt,
            attempt_count=result.attempt_count,
        )
        try:
            await (await self._context.writer.submit_async(unit))
        # A fallback that fails is the file's failure, not the URL's (design D2).
        except Exception as failure:
            self._context.stop.set("write_failed", failure)
