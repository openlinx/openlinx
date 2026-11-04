"""The transactional writer (015-add-crawl-store D4; 017-speed-up-crawl-writer D2, D3, D6)."""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from types import TracebackType
from typing import Any, Self, cast

from sqlalchemy import Connection, event, update

from openlinx.clock import Clock
from openlinx.output.codes import CRAWL_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.connections import (
    WRITER_BUSY_SECONDS,
    busy_error,
    is_busy,
    not_writable_name,
    opening,
)
from openlinx.store.schema import crawl

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
# Under a loop's commit deadline only the async calls wake the deadline, so a sync submit waits
# for 500 units, a flush or the close (023-fix-code-audit D5).
SYNC_IN_A_CRAWL = "inside a Crawl use submit_async / run_async"

type Unit[T] = Callable[[Connection], T]


class CrawlWriterClosedError(RuntimeError):
    """A unit or a flush reached a writer that was closed, or whose thread ended."""


class CrawlWriterReplayError(RuntimeError):
    """A unit did not do the same when it ran again, so the writer ended without that commit."""


class _Control(Enum):
    FLUSH = "flush"
    CLOSE = "close"


@dataclass(frozen=True)
class _Job:
    work: Unit[Any] | _Control
    done: Future[Any]
    # Resolved at its commit rather than when it has run.
    submitted: bool = False


@dataclass(frozen=True)
class _Ran:
    """A unit in the open transaction, with its first run's result and the rows it changed."""

    unit: Unit[Any]
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
        self._loop_deadline = False
        self._unflushed: asyncio.Event | None = None
        # Armed only while a unit runs, so the writer's own commits and rollbacks, a replay's
        # included, are not counted (design D6).
        self._in_unit = False
        # What the unit did to the transaction, in order: "commit" and "rollback".
        self._unit_ended: list[str] = []
        started: Future[None] = Future()
        self._thread = threading.Thread(
            target=self._serve, args=(started,), name=f"crawl writer {path.name}", daemon=True
        )
        self._thread.start()
        started.result()

    def run[T](self, unit: Unit[T]) -> T:
        self._refuse_under_the_loop_deadline()
        done: Future[T] = Future()
        self._submit(_Job(unit, done))
        return self._wait(done)

    async def run_async[T](self, unit: Unit[T]) -> T:
        done: Future[T] = Future()
        await self._submit_without_blocking(_Job(unit, done))
        with self._clock.off_loop():
            waiting = asyncio.wrap_future(done)
            while True:
                try:
                    return await asyncio.wait_for(asyncio.shield(waiting), ALIVE_CHECK_SECONDS)
                except TimeoutError:
                    self._check_alive(done)

    def submit[T](self, unit: Unit[T]) -> Future[T]:
        self._refuse_under_the_loop_deadline()
        done: Future[T] = _uncancellable()
        self._submit(_Job(unit, done, submitted=True))
        return done

    async def submit_async[T](self, unit: Unit[T]) -> asyncio.Future[T]:
        done: Future[T] = _uncancellable()
        await self._submit_without_blocking(_Job(unit, done, submitted=True))
        # Bound to this loop, so its callbacks run here and never on the writer thread. Not
        # held: the unit commits at the loop's commit deadline, which waits for clock time.
        return asyncio.wrap_future(done)

    @asynccontextmanager
    async def loop_deadline(self) -> AsyncIterator[None]:
        """The commit deadline on the loop's Clock, for a writer that an event loop drives, so a
        test's virtual clock sees it (020-add-crawl-core D7). The caller chooses it; from then
        on the thread commits on its own only after BATCH_SIZE units, a flush or the close, and
        the sync calls are refused, until the block ends."""
        self._unflushed = asyncio.Event()
        self._loop_deadline = True
        deadline = asyncio.create_task(self._flush_at_deadlines(self._unflushed))
        try:
            yield
        finally:
            deadline.cancel()
            with suppress(asyncio.CancelledError):
                await deadline
            self._loop_deadline = False
            self._unflushed = None

    async def _flush_at_deadlines(self, unflushed: asyncio.Event) -> None:
        while True:
            await unflushed.wait()
            await self._clock.sleep(COMMIT_AFTER_SECONDS)
            # A unit submitted from here on waits for the next deadline.
            unflushed.clear()
            try:
                await self.flush_async()
            # An ended writer keeps why it ended, and raises it to its next caller and at close.
            except Exception:
                return

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
        if isinstance(self._failure, OpenLinxError):
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
        if self._unflushed is not None:
            self._unflushed.set()
        try:
            self._submit(job, block=False)
        except Full:
            # Waits for room in the window or the queue without blocking the event loop; the
            # BATCH_SIZE-th unit commits without clock time, so room comes without it.
            with self._clock.off_loop():
                await asyncio.to_thread(self._submit, job)

    def _refuse_under_the_loop_deadline(self) -> None:
        if self._loop_deadline:
            raise RuntimeError(SYNC_IN_A_CRAWL)

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
                event.listen(connection, "commit", self._seen_commit)
                event.listen(connection, "rollback", self._seen_rollback)
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
        begun = connection.get_transaction()
        self._in_unit, self._unit_ended = True, []
        try:
            result, changes = _run_counted(job.work, connection)
        # KeyboardInterrupt too: it rolls back like any failure and reaches the unit's caller.
        except BaseException as error:
            self._in_unit = False
            if self._kept_its_transaction(job, job.work, connection, begun, error):
                self._replay(job, self._busy_error(error), connection)
            return True
        self._in_unit = False
        if not self._kept_its_transaction(job, job.work, connection, begun, None):
            return True
        identity = _compared_by_identity(result)
        if identity is not None:
            # Refused as a failing unit is: it leaves no change, and the batch runs again.
            self._replay(job, _identity_error(job.work, identity), connection)
            return True
        # Only units that succeeded run again, so a failing unit never does.
        self._batch.append(_Ran(job.work, result, changes, job.done if job.submitted else None))
        self._commit_if_due(connection)
        if not job.submitted:
            # Only now: a caller that reads after its unit returns sees the commit.
            job.done.set_result(result)
        return True

    def _seen_commit(self, connection: Connection) -> None:
        if self._in_unit:
            self._unit_ended.append("commit")

    def _seen_rollback(self, connection: Connection) -> None:
        if self._in_unit:
            self._unit_ended.append("rollback")

    def _kept_its_transaction(
        self,
        job: _Job,
        unit: Unit[Any],
        connection: Connection,
        begun: object,
        error: BaseException | None,
    ) -> bool:
        """False, or the writer ends, when the unit committed or rolled back the batch's
        transaction itself (design D6)."""
        ended = self._unit_ended
        if "commit" in ended:
            durable = ended[0] == "commit" and _batch_committed(connection, begun)
            raise self._committed(unit, connection, durable=durable) from error
        if ended:
            # The batch is gone, so it runs again, as after a failing unit; a busy file stays
            # crawl_busy, whatever the unit did after it.
            if error is not None and is_busy(error):
                failure = self._busy_error(error)
            else:
                failure = _rolled_back_error(unit)
                failure.__cause__ = error
            self._replay(job, failure, connection)
            return False
        return True

    def _committed(self, unit: Unit[Any], connection: Connection, *, durable: bool) -> RuntimeError:
        """A unit committed: its changes after the commit go, and the batch before it, which a
        commit that succeeded made permanent, resolves; the writer then ends, since a replay
        could no longer undo the batch (design D6)."""
        connection.rollback()
        if durable:
            self._settle(self._batch)
            self._batch = []
        return RuntimeError(
            f"the unit {_unit_name(unit)} committed, or tried to commit, the writer's "
            "transaction: never commit in a unit; the writer commits its batches"
        )

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
        if len(self._batch) >= BATCH_SIZE or (
            not self._loop_deadline
            and self._clock.monotonic() - self._first_uncommitted_at >= COMMIT_AFTER_SECONDS
        ):
            self._commit(connection)

    def _commit(self, connection: Connection) -> None:
        if not connection.in_transaction():
            return
        connection.commit()
        batch, self._batch = self._batch, []
        self._settle(batch)

    def _settle(self, batch: list[_Ran]) -> None:
        # Both the writer's own commit and a unit's commit make a batch durable.
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
        return OpenLinxError(
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


def _run_counted[T](unit: Unit[T], connection: Connection) -> tuple[T, int]:
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


def _compared_by_identity(result: object) -> str | None:
    """The name of a type in the result that compares by identity, which a replay's != could not
    check; per type, not per element, so a tuple of 500 records costs one check (design D6)."""
    kinds = {type(result)}
    if isinstance(result, tuple | list | set | frozenset):
        kinds.update(type(element) for element in result)
    elif isinstance(result, dict):
        kinds.update(type(key) for key in result)
        kinds.update(type(value) for value in result.values())
    for kind in kinds:
        # An enumeration member is a singleton: identity is its value.
        if kind.__eq__ is object.__eq__ and not issubclass(kind, Enum):
            return kind.__name__
    return None


def _batch_committed(connection: Connection, begun: object) -> bool:
    """Whether the unit's first commit, which came before any rollback of it, wrote the batch.

    SQLAlchemy fires its commit event before the commit runs. A commit that failed leaves the
    unit's transaction in place; one that the unit then rolled back leaves SQLAlchemy with no
    transaction, but SQLite still in the old one, since the rollback of a failed transaction
    reaches no driver (design D6)."""
    if connection.get_transaction() is begun:
        return False
    return connection.in_transaction() or not _driver(connection).in_transaction


def _unit_name(unit: Unit[Any]) -> str:
    return getattr(unit, "__qualname__", repr(unit))


def _rolled_back_error(unit: Unit[Any]) -> RuntimeError:
    return RuntimeError(
        f"the unit {_unit_name(unit)} rolled back the writer's transaction: never roll back in a "
        "unit; raise instead, and the writer rolls back the unit alone"
    )


def _identity_error(unit: Unit[Any], kind: str) -> TypeError:
    return TypeError(
        f"the unit {_unit_name(unit)} returned a {kind}, which compares by identity, so a "
        "replay cannot check it: return values, such as .all() rows or a record"
    )


def _replay_error(ran: _Ran, what: str) -> CrawlWriterReplayError:
    return CrawlWriterReplayError(f"The unit {_unit_name(ran.unit)} {what} when it ran again.")


def _fail_queued(queue: Queue[_Job], failure: BaseException | None) -> None:
    while True:
        try:
            job = queue.get_nowait()
        except Empty:
            return
        closed = CrawlWriterClosedError(CLOSED)
        closed.__cause__ = failure
        job.done.set_exception(closed)
