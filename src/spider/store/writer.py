"""The transactional writer (015-add-crawl-store D4; 017-speed-up-crawl-writer D2, D3, D6)."""

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future
from contextlib import suppress
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
# Submitted units unresolved at once: four batches, so the writer never waits for a submitter.
WINDOW = 2_000
COMMIT_AFTER_SECONDS = 1.0
# Real time between timer checks while no unit arrives; the timer itself reads the Clock.
IDLE_CHECK_SECONDS = 0.05
# How often a waiting caller checks that the writer thread is still there.
ALIVE_CHECK_SECONDS = 0.5
CLOSED = "The crawl writer is closed."


class CrawlWriterClosedError(RuntimeError):
    """A unit or a flush reached a writer that was closed, or whose thread ended."""


class CrawlWriterReplayError(RuntimeError):
    """A unit did not do the same when it ran again, so the writer ended without that commit."""


class _Control(Enum):
    FLUSH = "flush"
    CLOSE = "close"


@dataclass(frozen=True)
class _Job:
    work: Callable[[Connection], Any] | _Control
    done: Future[Any]
    # Resolved at its commit rather than when it has run.
    submitted: bool = False


@dataclass(frozen=True)
class _Ran:
    """A unit in the open transaction, with its first run's result and the rows it changed."""

    unit: Callable[[Connection], Any]
    result: Any
    changes: int
    future: Future[Any] | None = None


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
        # Signalled when a commit or a failing unit frees room in the window.
        self._room = threading.Condition(self._lock)
        self._unresolved = 0
        self._closed = False
        # Set once the writer thread drains its queue on the way out.
        self._ended = False
        self._failure: BaseException | None = None
        # Owned by the writer thread: the units in the open transaction, which a failing unit makes
        # run again, and the time of the first one.
        self._batch: list[_Ran] = []
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
        await self._submit_without_blocking(_Job(unit, done))
        with self._clock.off_loop():
            waiting = asyncio.wrap_future(done)
            while True:
                try:
                    return await asyncio.wait_for(asyncio.shield(waiting), ALIVE_CHECK_SECONDS)
                except TimeoutError:
                    self._check_alive(done)

    def submit[T](self, unit: Callable[[Connection], T]) -> Future[T]:
        done: Future[T] = _uncancellable()
        self._submit(_Job(unit, done, submitted=True))
        return done

    async def submit_async[T](self, unit: Callable[[Connection], T]) -> asyncio.Future[T]:
        done: Future[T] = _uncancellable()
        await self._submit_without_blocking(_Job(unit, done, submitted=True))
        # Bound to this loop, so its callbacks run here and never on the writer thread. Not
        # held: the unit commits after BATCH_SIZE units or a second of clock time.
        return asyncio.wrap_future(done)

    async def flush_async(self) -> None:
        with self._clock.off_loop():
            await asyncio.to_thread(self.flush)

    async def close_async(self) -> None:
        with self._clock.off_loop():
            await asyncio.to_thread(self.close)

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
            # A writer that ends meanwhile fails this job; why it ended is raised below.
            with suppress(CrawlWriterClosedError):
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
        with self._room:
            while job.submitted and self._unresolved >= WINDOW and not self._closed:
                if not block:
                    raise Full
                self._room.wait()
            if self._closed:
                raise CrawlWriterClosedError(CLOSED) from self._failure
            if job.submitted:
                self._unresolved += 1
        try:
            self._queue.put(job, block=block)
        except Full:
            if job.submitted:
                self._free(1)
            raise
        with self._lock:
            ended = self._ended
        # Queued after the writer drained its queue on the way out, so it would never complete.
        if ended:
            _fail_queued(self._queue, self._failure)

    async def _submit_without_blocking(self, job: _Job) -> None:
        try:
            self._submit(job, block=False)
        except Full:
            # Waits for room in the window or the queue without blocking the event loop; the
            # BATCH_SIZE-th unit commits without clock time, so room comes without it.
            with self._clock.off_loop():
                await asyncio.to_thread(self._submit, job)

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
            raise CrawlWriterClosedError(CLOSED) from self._failure

    def _serve(self, started: Future[None]) -> None:
        try:
            with (
                opening(self._path, role="write", busy_seconds=self._busy_seconds) as engine,
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
            with self._room:
                self._closed = self._ended = True
                # A submit that waits for room would otherwise wait forever.
                self._room.notify_all()
            _fail_queued(self._queue, self._failure)

    def _work(self, connection: Connection) -> None:
        while True:
            try:
                job: _Job | None = self._queue.get(timeout=IDLE_CHECK_SECONDS)
            except Empty:
                job = None
            try:
                if job is None:
                    self._commit_if_due(connection)
                elif not self._handle(job, connection):
                    return
            except BaseException as error:
                failure = self._busy_error(error)
                self._end(failure, job)
                if failure is error:
                    raise
                raise failure from error

    def _end(self, failure: BaseException, job: _Job | None) -> None:
        # Closed first, so a submit after anyone learns of the failure fails at once.
        with self._lock:
            self._failure, self._closed = failure, True
        # A failed commit ends the writer: the caller of the job in hand and every submitted
        # unit of the open transaction learn why.
        waiting = [ran.future for ran in self._batch if ran.future is not None]
        if job is not None:
            waiting.append(job.done)
        for done in waiting:
            if not done.done():
                done.set_exception(failure)

    def _handle(self, job: _Job, connection: Connection) -> bool:
        if isinstance(job.work, _Control):
            self._commit(connection)
            if job.work is _Control.CLOSE:
                # Readers that stay open would otherwise keep the WAL from shrinking. Run on the
                # driver's connection: through SQLAlchemy it would begin a transaction first.
                _driver(connection).execute("PRAGMA wal_checkpoint(TRUNCATE)")
            job.done.set_result(None)
            return job.work is _Control.FLUSH
        if not connection.in_transaction():
            self._begin(connection)
        # No savepoint: one per unit costs more than replaying the batch when a unit fails.
        try:
            result, changes = _run_counted(job.work, connection)
        # KeyboardInterrupt too: it rolls back like any failure and reaches the unit's caller.
        except BaseException as error:
            self._replay(job, self._busy_error(error), connection)
            return True
        # Only units that succeeded run again, so a failing unit never does.
        self._batch.append(_Ran(job.work, result, changes, job.done if job.submitted else None))
        self._commit_if_due(connection)
        if not job.submitted:
            # Only now: a caller that reads after its unit returns sees the commit.
            job.done.set_result(result)
        return True

    def _begin(self, connection: Connection) -> None:
        connection.begin()
        self._first_uncommitted_at = self._clock.monotonic()

    def _replay(self, failed: _Job, error: BaseException, connection: Connection) -> None:
        try:
            connection.rollback()
            if self._batch:
                self._begin(connection)
                for ran in self._batch:
                    _run_again(ran, connection)
                self._commit(connection)
        except BaseException as replay_error:
            failure = self._busy_error(replay_error)
            # Ended before the failing unit's caller learns its error, so a submit it then makes
            # fails at once.
            self._end(failure, None)
            if failure is replay_error:
                raise
            raise failure from replay_error
        finally:
            # Its own error even when the replay fails and ends the writer (design D6).
            failed.done.set_exception(error)
            if failed.submitted:
                self._free(1)

    def _commit_if_due(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        waited = self._clock.monotonic() - self._first_uncommitted_at
        if len(self._batch) >= BATCH_SIZE or waited >= COMMIT_AFTER_SECONDS:
            self._commit(connection)

    def _commit(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        connection.commit()
        batch, self._batch = self._batch, []
        resolved = 0
        for ran in batch:
            if ran.future is not None:
                ran.future.set_result(ran.result)
                resolved += 1
        self._free(resolved)
        if self._on_commit is not None and batch:
            self._on_commit(len(batch))

    def _free(self, slots: int) -> None:
        if not slots:
            return
        with self._room:
            self._unresolved -= slots
            self._room.notify_all()

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


def _uncancellable[T]() -> Future[T]:
    done: Future[T] = Future()
    # So cancel() returns False: a cancelled Future would end the writer at its commit, for
    # every caller, and the unit is never withdrawn anyway (design D2).
    done.set_running_or_notify_cancel()
    return done


def _check_writable(connection: Connection) -> None:
    # A write that is rolled back, so an unwritable file fails before anything is crawled.
    transaction = connection.begin()
    connection.execute(update(crawl).values(id=crawl.c.id))
    transaction.rollback()


def _driver(connection: Connection) -> sqlite3.Connection:
    return cast(sqlite3.Connection, connection.connection.driver_connection)


def _run_counted[T](unit: Callable[[Connection], T], connection: Connection) -> tuple[T, int]:
    driver = _driver(connection)
    before = driver.total_changes
    result = unit(connection)
    # SQLite's count is a C int, which wraps on a long Crawl.
    return result, (driver.total_changes - before) & 0xFFFFFFFF


def _run_again(ran: _Ran, connection: Connection) -> None:
    # A unit that does not do the same again ends the writer, never just its own changes: its
    # caller holds the first run's result, and may have built later units on it (design D6).
    try:
        result, changes = _run_counted(ran.unit, connection)
    except BaseException as error:
        # Kept as it is, so a busy file still ends the writer with crawl_busy.
        if is_busy(error):
            raise
        raise _replay_error(ran, "raised") from error
    if result != ran.result:
        raise _replay_error(ran, "returned a different result")
    if changes != ran.changes:
        raise _replay_error(ran, f"changed {changes} rows instead of {ran.changes}")


def _replay_error(ran: _Ran, what: str) -> CrawlWriterReplayError:
    name = getattr(ran.unit, "__qualname__", repr(ran.unit))
    return CrawlWriterReplayError(f"The unit {name} {what} when it ran again.")


def _fail_queued(queue: Queue[_Job], failure: BaseException | None) -> None:
    while True:
        try:
            job = queue.get_nowait()
        except Empty:
            return
        closed = CrawlWriterClosedError(CLOSED)
        closed.__cause__ = failure
        job.done.set_exception(closed)
