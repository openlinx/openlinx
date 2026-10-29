"""Progress events: the urls counts kept from committed units, written every 10 seconds
(020-add-crawl-core D10)."""

from collections.abc import Callable
from itertools import count

from spider.clock import Clock
from spider.crawl.engine.warning_log import WarningLog
from spider.store.records import UrlCounts, UrlTally

PROGRESS_SECONDS = 10


class UrlCounters:
    """Seeded once a run by a counting query, then kept from the tallies of committed units, so
    no event counts over urls, which a GROUP BY would scan (design D10)."""

    def __init__(self, counts: UrlCounts) -> None:
        self._tally = UrlTally(
            discovered=counts.discovered,
            fetched=counts.fetched,
            errors=counts.errors,
            skipped=counts.skipped,
            queued=counts.queued,
        )

    def add(self, tally: UrlTally) -> None:
        self._tally += tally

    def to_json(self) -> dict[str, int]:
        tally = self._tally
        return {
            "discovered": tally.discovered,
            "fetched": tally.fetched,
            "errors": tally.errors,
            "skipped": tally.skipped,
            "queued": tally.queued,
        }


async def report_progress(
    *,
    clock: Clock,
    warnings: WarningLog,
    crawl_id: str,
    counters: UrlCounters,
    rate: Callable[[float], float],
    paused: Callable[[], bool],
) -> None:
    """Writes a progress event every 10 seconds of clock time from the run's start, during a
    network pause too, until it is cancelled. `rate` gives the requests per second for the
    seconds the run has lasted."""
    started = clock.monotonic()
    for tick in count(1):
        await clock.sleep(started + tick * PROGRESS_SECONDS - clock.monotonic())
        elapsed = clock.monotonic() - started
        warnings.event(
            "progress",
            crawl_id=crawl_id,
            elapsed_s=round(elapsed, 3),
            urls=counters.to_json(),
            rate=rate(elapsed),
            paused=paused(),
        )
