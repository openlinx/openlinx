"""The transactional writer: units of work on one thread (design D4 of 015-add-crawl-store)."""

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from types import TracebackType
from typing import Any, Self, cast

from sqlalchemy import Connection, update

from spider.clock import Clock
from spider.output.codes import CRAWL_NOT_WRITABLE
from spider.output.diagnostics import SpiderError
from spider.store.connections import (
    WRITER_BUSY_SECONDS,
    busy_error,
    is_busy,
    not_writable_name,
    opening,
)
from spider.store.schema import crawl

QUEUE_SIZE = 50_000
BATCH_SIZE = 500
COMMIT_AFTER_SECONDS = 1.0
# Real time between timer checks while no unit arrives; the timer itself reads the Clock.
IDLE_CHECK_SECONDS = 0.05
# How often a waiting caller checks that the writer thread is still there.
ALIVE_CHECK_SECONDS = 0.5
CLOSED = "The crawl writer is closed."


class CrawlWriterClosedError(RuntimeError):
    """A unit or a flush reached a writer that was closed, or whose thread ended."""


class _Control(Enum):
    FLUSH = "flush"
    CLOSE = "close"


@dataclass(frozen=True)
class _Job:
    work: Callable[[Connection], Any] | _Control
    done: Future[Any]


class CrawlWriter:
    def __init__(
        self,
        path: Path,
        clock: Clock,
        on_commit: Callable[[int], None] | None = None,
        busy_seconds: float = WRITER_BUSY_SECONDS,
    ) -> None:
        self._path = path
        self._busy_seconds = busy_seconds
        self._clock = clock
        self._on_commit = on_commit
        self._queue: Queue[_Job] = Queue(maxsize=QUEUE_SIZE)
        self._lock = threading.Lock()
        self._closed = False
        self._failure: BaseException | None = None
        # Owned by the writer thread: units since the last commit, those that left a change, and
        # the time of the first one.
        self._uncommitted = 0
        self._succeeded = 0
        self._first_uncommitted_at = 0.0
        started: Future[None] = Future()
        self._thread = threading.Thread(
            target=self._serve, args=(started,), name=f"crawl writer {path.name}", daemon=True
        )
        self._thread.start()
        started.result()

    def run[T](self, unit: Callable[[Connection], T]) -> T:
        done: Future[T] = Future()
        self._submit(_Job(unit, done))
        return self._wait(done)

    async def run_async[T](self, unit: Callable[[Connection], T]) -> T:
        done: Future[T] = Future()
        job = _Job(unit, done)
        try:
            self._submit(job, block=False)
        except Full:
            # Backpressure without blocking the event loop.
            await asyncio.to_thread(self._submit, job)
        waiting = asyncio.wrap_future(done)
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(waiting), ALIVE_CHECK_SECONDS)
            except TimeoutError:
                self._check_alive(done)

    def flush(self) -> None:
        done: Future[None] = Future()
        self._submit(_Job(_Control.FLUSH, done))
        self._wait(done)

    def close(self) -> None:
        self._refuse_own_thread()
        with self._lock:
            already, self._closed = self._closed, True
        if not already and self._thread.is_alive():
            done: Future[None] = Future()
            self._queue.put(_Job(_Control.CLOSE, done))
            self._wait(done)
        self._thread.join()
        # Not wrapped: leaving a with block after a busy unit must still exit with crawl_busy.
        if isinstance(self._failure, SpiderError):
            raise self._failure
        # A commit that failed while no unit was waiting would otherwise lose units silently.
        if self._failure is not None:
            raise CrawlWriterClosedError(CLOSED) from self._failure

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _submit(self, job: _Job, *, block: bool = True) -> None:
        self._refuse_own_thread()
        with self._lock:
            if self._closed:
                raise CrawlWriterClosedError(CLOSED)
        self._queue.put(job, block=block)

    def _refuse_own_thread(self) -> None:
        # A unit that waited for its own writer would wait forever.
        if threading.current_thread() is self._thread:
            raise RuntimeError("A unit cannot submit work to the writer that runs it.")

    def _wait[T](self, done: Future[T]) -> T:
        while True:
            try:
                return done.result(timeout=ALIVE_CHECK_SECONDS)
            except TimeoutError:
                self._check_alive(done)

    def _check_alive(self, done: Future[Any]) -> None:
        # A job queued after the thread drained the queue on its way out would wait forever.
        if not self._thread.is_alive() and not done.done():
            raise CrawlWriterClosedError(CLOSED)

    def _serve(self, started: Future[None]) -> None:
        try:
            with (
                opening(self._path, busy_seconds=self._busy_seconds) as engine,
                engine.connect() as connection,
            ):
                _check_writable(connection)
                started.set_result(None)
                self._work(connection)
        except BaseException as error:
            # Never raised on this thread, whose traceback would reach stderr as raw text.
            if started.done():
                self._failure = error
            else:
                started.set_exception(self._open_error(error))
        finally:
            with self._lock:
                self._closed = True
            _fail_queued(self._queue)

    def _work(self, connection: Connection) -> None:
        while True:
            try:
                job = self._queue.get(timeout=IDLE_CHECK_SECONDS)
            except Empty:
                self._commit_if_due(connection)
                continue
            try:
                if not self._handle(job, connection):
                    return
            except BaseException as error:
                failure = self._busy_error(error)
                # A failed commit ends the writer; the caller of the job in hand learns why.
                if not job.done.done():
                    job.done.set_exception(failure)
                if failure is error:
                    raise
                raise failure from error

    def _handle(self, job: _Job, connection: Connection) -> bool:
        if isinstance(job.work, _Control):
            self._commit(connection)
            if job.work is _Control.CLOSE:
                # Readers that stay open would otherwise keep the WAL from shrinking. Run on the
                # driver's connection: through SQLAlchemy it would begin a transaction first.
                driver = cast(sqlite3.Connection, connection.connection.driver_connection)
                driver.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            job.done.set_result(None)
            return job.work is _Control.FLUSH
        if not connection.in_transaction():
            connection.begin()
            self._uncommitted, self._succeeded = 0, 0
            self._first_uncommitted_at = self._clock.monotonic()
        result, error = _run(job.work, connection)
        if error is not None:
            error = self._busy_error(error)
        self._uncommitted += 1
        self._succeeded += error is None
        self._commit_if_due(connection)
        # Only now: a caller that reads after its unit returns sees the commit.
        if error is None:
            job.done.set_result(result)
        else:
            job.done.set_exception(error)
        return True

    def _commit_if_due(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        waited = self._clock.monotonic() - self._first_uncommitted_at
        if self._uncommitted >= BATCH_SIZE or waited >= COMMIT_AFTER_SECONDS:
            self._commit(connection)

    def _commit(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        connection.commit()
        if self._on_commit is not None and self._succeeded:
            self._on_commit(self._succeeded)

    def _busy_error(self, error: BaseException) -> BaseException:
        if not is_busy(error):
            return error
        return busy_error(self._path, "writing", self._busy_seconds, error)

    def _open_error(self, error: BaseException) -> BaseException:
        busy = self._busy_error(error)
        if busy is not error:
            return busy
        name = not_writable_name(error)
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


def _run(
    unit: Callable[[Connection], Any], connection: Connection
) -> tuple[Any, BaseException | None]:
    savepoint = connection.begin_nested()
    try:
        result = unit(connection)
    # KeyboardInterrupt too: it rolls back like any failure and reaches the unit's caller.
    except BaseException as error:
        savepoint.rollback()
        return None, error
    savepoint.commit()
    return result, None


def _fail_queued(queue: Queue[_Job]) -> None:
    while True:
        try:
            job = queue.get_nowait()
        except Empty:
            return
        job.done.set_exception(CrawlWriterClosedError(CLOSED))
