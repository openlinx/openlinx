"""The transactional writer: units of work on one thread (design D4 of 015-add-crawl-store)."""

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from types import TracebackType
from typing import Any, Literal, Self

from sqlalchemy import Connection, update

from spider.clock import Clock
from spider.output.codes import CRAWL_NOT_WRITABLE
from spider.output.diagnostics import SpiderError
from spider.store.connections import cannot_write, opening
from spider.store.schema import crawl

QUEUE_SIZE = 50_000
BATCH_SIZE = 500
COMMIT_AFTER_SECONDS = 1.0
# Real time between timer checks while no unit arrives; the timer itself reads the Clock.
IDLE_CHECK_SECONDS = 0.05


@dataclass(frozen=True)
class _Job:
    unit: Callable[[Connection], Any] | Literal["flush", "close"]
    done: Future[Any]


class CrawlWriter:
    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._queue: Queue[_Job] = Queue(maxsize=QUEUE_SIZE)
        # Owned by the writer thread: units and the time of the first one since the last commit.
        self._uncommitted = 0
        self._first_uncommitted_at = 0.0
        started: Future[None] = Future()
        self._thread = threading.Thread(
            target=self._serve, args=(started,), name=f"crawl writer {path.name}", daemon=True
        )
        self._thread.start()
        started.result()

    def run[T](self, unit: Callable[[Connection], T]) -> T:
        done: Future[T] = Future()
        self._queue.put(_Job(unit, done))
        return done.result()

    def flush(self) -> None:
        done: Future[None] = Future()
        self._queue.put(_Job("flush", done))
        done.result()

    def close(self) -> None:
        done: Future[None] = Future()
        self._queue.put(_Job("close", done))
        done.result()
        self._thread.join()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _serve(self, started: Future[None]) -> None:
        try:
            with opening(self._path) as engine, engine.connect() as connection:
                _check_writable(connection)
                started.set_result(None)
                self._work(connection)
        except BaseException as error:
            if started.done():
                raise
            # Before any unit: the caller that opened the writer gets the error, not the thread.
            started.set_exception(self._open_error(error))

    def _work(self, connection: Connection) -> None:
        while True:
            try:
                job = self._queue.get(timeout=IDLE_CHECK_SECONDS)
            except Empty:
                self._commit_if_due(connection)
                continue
            if isinstance(job.unit, str):
                connection.commit()
                job.done.set_result(None)
                if job.unit == "close":
                    return
                continue
            if not connection.in_transaction():
                connection.begin()
                self._uncommitted, self._first_uncommitted_at = 0, self._clock.monotonic()
            result, error = _run(job.unit, connection)
            self._uncommitted += 1
            self._commit_if_due(connection)
            # Only now: a caller that reads after its unit returns sees the commit.
            if error is None:
                job.done.set_result(result)
            else:
                job.done.set_exception(error)

    def _commit_if_due(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        waited = self._clock.monotonic() - self._first_uncommitted_at
        if self._uncommitted >= BATCH_SIZE or waited >= COMMIT_AFTER_SECONDS:
            connection.commit()

    def _open_error(self, error: BaseException) -> BaseException:
        name = cannot_write(error)
        if name is None:
            return error
        return SpiderError(
            CRAWL_NOT_WRITABLE,
            f"Cannot write the crawl file {self._path}.",
            hint="Check that the file and its folder are writable, and not read-only.",
            details={"file": str(self._path), "error": name},
        )


def _check_writable(connection: Connection) -> None:
    # A write that is rolled back, so an unwritable file fails before anything is crawled.
    transaction = connection.begin()
    connection.execute(update(crawl).values(id=crawl.c.id))
    transaction.rollback()


def _run(unit: Callable[[Connection], Any], connection: Connection) -> tuple[Any, Exception | None]:
    savepoint = connection.begin_nested()
    try:
        result = unit(connection)
    except Exception as error:
        savepoint.rollback()
        return None, error
    savepoint.commit()
    return result, None
