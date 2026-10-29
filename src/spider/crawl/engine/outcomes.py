"""Every unit's outcome, and the fallback of a URL whose unit failed (020-add-crawl-core D2)."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from spider.crawl.engine.crawl_warnings import record_failure
from spider.crawl.engine.hooks import UrlResult
from spider.crawl.engine.progress import UrlCounters
from spider.crawl.engine.stop import StopSignal
from spider.crawl.engine.warning_log import WarningLog
from spider.output.diagnostics import Diagnostic
from spider.store.failures import is_one_urls_failure
from spider.store.records import Provenance, Recording
from spider.store.urls import UrlUnit, record_unwritten
from spider.store.writer import CrawlWriter, CrawlWriterClosedError

# URL units in a row that fail on their first run: a broken handler or store writer, not a
# hundred bad URLs, so the Crawl fails instead of recording the rest of the site as errors.
RECORD_FAILURE_LIMIT = 100


class RecordingFailedError(Exception):
    """Recording kept failing for one URL after another (design D16)."""


@dataclass(frozen=True, slots=True)
class Recorded:
    """A URL's final state, the unit that records it, and its handlers' failure, which counts
    once the unit has recorded the URL: a skip it overtook leaves the URL to be decided again."""

    result: UrlResult
    unit: UrlUnit
    handler_failure: Diagnostic | None = None


class Outcomes:
    """Every submitted unit's Future until its outcome has reached the engine (design D2)."""

    def __init__(
        self, writer: CrawlWriter, reporter: WarningLog, stop: StopSignal, counters: UrlCounters
    ) -> None:
        self._writer = writer
        self._reporter = reporter
        self._stop = stop
        self._counters = counters
        self._pending: set[asyncio.Future[Any]] = set()
        self._failed_in_a_row = 0

    async def submit(self, recorded: Recorded) -> None:
        future = await self._writer.submit_async(recorded.unit)
        self._pending.add(future)
        future.add_done_callback(lambda done: self._unit_done(recorded, done))

    async def settled(self) -> None:
        """Waits for every outcome, fallback units included."""
        while self._pending:
            # The writer commits on its own only every 500 units or second of clock time.
            with suppress(CrawlWriterClosedError):
                # An ended writer has already failed every Future it held.
                await self._writer.flush_async()
            # Outcomes that the flush resolved have already left the set.
            if self._pending:
                await asyncio.wait(set(self._pending))

    def _unit_done(self, recorded: Recorded, done: asyncio.Future[Recording]) -> None:
        self._pending.discard(done)
        error = done.exception()
        result, failure = recorded.result, recorded.handler_failure
        if failure is not None and (error is not None or done.result().recorded):
            self._reporter.count(failure, result.url)
        if error is None:
            # At the commit, as the file then shows it (design D10).
            self._counters.add(done.result().tally)
            self._failed_in_a_row = 0
            return
        if not is_one_urls_failure(error):
            self._stop.set("write_failed", error)
            return
        self._reporter.count(record_failure(result.url, error), result.url)
        self._failed_in_a_row += 1
        if self._failed_in_a_row >= RECORD_FAILURE_LIMIT:
            failed = RecordingFailedError(
                f"{RECORD_FAILURE_LIMIT} URLs in a row could not be recorded, the last with "
                f"{type(error).__name__}: {error}"
            )
            failed.__cause__ = error
            self._stop.set("write_failed", failed)
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
            recording = await (await self._writer.submit_async(unit))
            self._counters.add(recording.tally)
        # A fallback that fails is the file's failure, not the URL's (design D2).
        except Exception as failure:
            self._stop.set("write_failed", failure)


def provenance_of(result: UrlResult) -> Provenance:
    return Provenance(
        crawl_depth=result.crawl_depth,
        discovered_via=result.discovered_via,
        found_on_url_id=result.found_on_url_id,
    )
