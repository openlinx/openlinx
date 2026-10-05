"""The transactional writer: units of work on one thread (design D4 of 015-add-crawl-store)."""

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
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
# How often a waiting caller checks that the writer thread is still there.
ALIVE_CHECK_SECONDS = 0.5
CLOSED = "The crawl writer is closed."


class CrawlWriterClosedError(RuntimeError):
    """A unit or a flush reached a writer that was closed, or whose thread ended."""


@dataclass(frozen=True)
class _Job:
    unit: Callable[[Connection], Any] | Literal["flush", "close"]
    done: Future[Any]


class CrawlWriter:
    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._queue: Queue[_Job] = Queue(maxsize=QUEUE_SIZE)
        self._closing = threading.Lock()
        self._closed = False
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
        self._submit(_Job("flush", done))
        self._wait(done)

    def close(self) -> None:
        with self._closing:
            if self._closed:
                return
            self._closed = True
        if self._thread.is_alive():
            done: Future[None] = Future()
            self._queue.put(_Job("close", done))
            self._wait(done)
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

    def _submit(self, job: _Job, *, block: bool = True) -> None:
        if self._closed:
            raise CrawlWriterClosedError(CLOSED)
        self._queue.put(job, block=block)

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
            with opening(self._path) as engine, engine.connect() as connection:
                _check_writable(connection)
                started.set_result(None)
                self._work(connection)
        except BaseException as error:
            # Never raised on this thread: its caller already has it, and a thread's traceback
            # would reach stderr as raw text.
            if not started.done():
                started.set_exception(self._open_error(error))
        finally:
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
                if not self._do(job, connection):
                    return
            except BaseException as error:
                # A failed commit ends the writer; the caller of the job in hand learns why.
                if not job.done.done():
                    job.done.set_exception(error)
                raise

    def _do(self, job: _Job, connection: Connection) -> bool:
        if isinstance(job.unit, str):
            connection.commit()
            job.done.set_result(None)
            return job.unit != "close"
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
        return True

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
