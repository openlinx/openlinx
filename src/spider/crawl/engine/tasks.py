"""The run's URL tasks, tracked until each ends, with the first that ended on a bug, and the
run's dependencies that the units share (020-add-crawl-core D3, D16)."""

import asyncio
from dataclasses import dataclass

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.pause import NetworkPause, Redispatch
from spider.crawl.engine.stop import StopGrace, StopSignal
from spider.crawl.fetch.politeness import BlockingRuns, RequestLimits
from spider.crawl.fetch.requester import Requester
from spider.crawl.robots.loader import RobotsLoader
from spider.store.failures import is_write_failure


class TaskFailure:
    """Tracks the run's URL tasks until each ends, keeps the Checked URLs' in flight, and keeps
    the first exception that escaped one: a bug, which ends the run (design D16)."""

    def __init__(self, stop: StopSignal) -> None:
        self._stop = stop
        self._error: BaseException | None = None
        # The tasks of Checked URLs in flight, which never hold the depth barrier (design D3).
        self.checked_urls: set[asyncio.Task[None]] = set()

    @property
    def is_set(self) -> bool:
        return self._error is not None

    def track(self, tasks: set[asyncio.Task[None]], task: asyncio.Task[None]) -> None:
        tasks.add(task)
        task.add_done_callback(lambda done: self._ended(tasks, done))

    def raise_first(self) -> None:
        if self._error is not None:
            raise self._error

    def _ended(self, tasks: set[asyncio.Task[None]], task: asyncio.Task[None]) -> None:
        tasks.discard(task)
        if task.cancelled():
            return
        # Retrieved here, since a task that ends before a gather waits on it has already left
        # its set: unseen, its URL would stay queued and be dispatched again by every sweep.
        error = task.exception()
        if error is not None and is_write_failure(error):
            # Not a bug: the writer ended, or the file refused a write outside the URL's unit,
            # such as its origin's robots.txt row.
            self._stop.write_failed(error)
        elif error is not None and self._error is None:
            self._error = error


@dataclass(frozen=True, slots=True, kw_only=True)
class Run:
    """One run's dependencies, made once by run_crawl."""

    context: CrawlContext
    outcomes: Outcomes
    limits: RequestLimits
    requester: Requester
    robots: RobotsLoader
    blocking: BlockingRuns
    task_failure: TaskFailure
    pause: NetworkPause
    redispatch: Redispatch
    grace: StopGrace
