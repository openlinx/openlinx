"""Prepare Pages in spawn workers and contain failures at the worker boundary."""

import asyncio
import multiprocessing
import signal
import sys
import threading
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from multiprocessing.connection import _ConnectionBase, wait
from multiprocessing.process import BaseProcess
from time import monotonic
from typing import Any

from openlinx.clock import SystemClock
from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.parse_wire import Outcome, crashed_page, decode_outcome, encode_outcome
from openlinx.crawl.pages.preparation import PageSettings, PreparedPage, prepare_page
from openlinx.crawl.urls import NormalizedUrl

# Pages that may wait for a busy worker, per worker (design D2).
BACKLOG_PER_WORKER = 2
# From the moment a worker takes a Page; no flag (design D8). Also how long a worker may take
# to answer ready.
PREPARE_DEADLINE_SECONDS = 30.0
_SHUTDOWN_GRACE = 10.0
_REAP_SECONDS = 5.0
_WINDOWS_WAIT_HANDLES = 63
# A worker's first answer; an outcome is a pickle, which never starts with these bytes.
_READY = b"ready"
_START_FAILED = b"failed:"

# A Connection on POSIX, a PipeConnection on Windows: the one class both pipe ends share.
type _PipeEnd = _ConnectionBase[Any, Any]
type _Work = tuple[NormalizedUrl, FetchResult]


class WorkerStartError(RuntimeError):
    """A worker could not read its snapshot, or ended before it was ready: the Crawl's error."""


def _work(tasks: _PipeEnd, results: _PipeEnd) -> None:
    """A worker's life; the snapshot is its first message, so it is pickled once (design D1)."""
    # Ctrl+C reaches every process of a console: the crawl process ends its workers in order.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    try:
        settings: PageSettings = tasks.recv()
    except (EOFError, OSError):
        return
    # A snapshot it cannot read, such as an extractor whose module it cannot import.
    except Exception as error:
        with suppress(OSError):
            results.send_bytes(_START_FAILED + f"{type(error).__name__}: {error}".encode())
        return
    try:
        results.send_bytes(_READY)
    except OSError:
        return
    while True:
        try:
            work = tasks.recv()
        # The crawl process ended without stopping this worker: nothing is left to do.
        except (EOFError, OSError):
            return
        if work is None:
            return
        url, response = work
        outcome: Outcome
        try:
            outcome = prepare_page(url, response, settings)
        except Exception as error:
            outcome = error
        try:
            results.send_bytes(encode_outcome(outcome))
        # As at recv: the crawl process ended while this worker prepared its Page.
        except OSError:
            return


def worker_limit(platform: str, version: tuple[int, int]) -> int | None:
    """The most workers the waiter thread can watch, or None for no limit (design D1)."""
    # connection.wait takes at most 63 handles on Windows before Python 3.13, and the waiter
    # watches one per worker, its result pipe, and its own wake pipe.
    if platform == "win32" and version < (3, 13):
        return _WINDOWS_WAIT_HANDLES - 1
    return None


def _reap(process: BaseProcess) -> None:
    # Killed first, so that the join is bounded: an ended worker may still be exiting.
    process.kill()
    _join_process(process, monotonic() + _REAP_SECONDS)
    process.close()


def _join_process(process: BaseProcess, deadline: float) -> None:
    # Another observer can already have reaped the child; the sentinel still records exit.
    if not wait([process.sentinel], max(0.0, deadline - monotonic())):
        raise RuntimeError(f"The parse worker {process.name} did not end.")
    process.join(0)


@dataclass(frozen=True, eq=False)
class _Worker:
    process: BaseProcess
    # The crawl process writes work to one pipe and reads outcomes from the other, so the event
    # loop's sends and the waiter thread's receives never share a connection.
    tasks: _PipeEnd
    results: _PipeEnd


@dataclass(frozen=True, eq=False)
class _Held:
    url: NormalizedUrl
    future: asyncio.Future[PreparedPage]
    deadline: asyncio.Task[None]


class PoolExecutor:
    """Prepares each Page in one of `workers` spawn processes, one Page per worker at a time."""

    def __init__(
        self,
        workers: int,
        deadline: float = PREPARE_DEADLINE_SECONDS,
        ready_deadline: float = PREPARE_DEADLINE_SECONDS,
    ) -> None:
        self.workers = workers
        limit = worker_limit(sys.platform, (sys.version_info.major, sys.version_info.minor))
        if self.workers < 1 or (limit is not None and self.workers > limit):
            raise ValueError(
                f"{self.workers} parse workers: the pool runs at least 1"
                + ("" if limit is None else f" and at most {limit} here")
            )
        self.backlog = BACKLOG_PER_WORKER * self.workers
        self._deadline = deadline
        self._ready_deadline = ready_deadline
        # Process readiness and termination use real elapsed time, even in embedded Crawls.
        self._clock = SystemClock()
        self._settings: PageSettings | None = None
        # The workers not yet retired, and those still running, idle or busy, or ready; a
        # worker that ended is retired, so a long hostile Crawl keeps no pipe or process of
        # it. The count supplies distinct names for replacements.
        self._workers: list[_Worker] = []
        self._spawned = 0
        self._live: set[_Worker] = set()
        self._ready: set[_Worker] = set()
        self._idle: deque[_Worker] = deque()
        # The Page each busy worker holds, and the timer of its deadline (design D8).
        self._busy: dict[_Worker, _Held] = {}
        # The timer of each worker's ready answer.
        self._readiness: dict[_Worker, asyncio.Task[None]] = {}
        self._waiting: deque[tuple[_Work, asyncio.Future[PreparedPage]]] = deque()
        # Each ended worker's retirement, which starts its replacement.
        self._retiring: set[asyncio.Task[None]] = set()
        self._started = False
        self._closing = False
        self._close_task: asyncio.Task[None] | None = None
        self._broken: BaseException | None = None
        # The result pipes the waiter thread reads, by identity: on Windows a pipe end is a
        # PipeConnection, which is no Connection. The loop's thread adds, the waiter removes.
        self._watched: dict[int, _Worker] = {}
        # Result pipe ends no longer watched, which the waiter closes, since it may still be
        # waiting on them.
        self._retired: list[_PipeEnd] = []
        self._watched_lock = threading.Lock()
        self._waiter: threading.Thread | None = None
        # True: watch the pipes again, for a replacement; None: stop.
        self._wake_reader, self._wake_writer = multiprocessing.Pipe(duplex=False)

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings
        for _ in range(self.workers):
            await self._spawn()
        # A daemon: nothing it waits for may keep the crawl process from exiting.
        self._waiter = threading.Thread(
            target=self._wait_for_outcomes,
            args=(asyncio.get_running_loop(),),
            name="parse-worker-waiter",
            daemon=True,
        )
        self._waiter.start()
        self._started = True

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        if self._closing:
            raise RuntimeError("the parse pool prepares a Page after close")
        if not self._started:
            raise RuntimeError("the parse pool prepares a Page before it is started")
        if self._broken is not None:
            raise self._broken
        future: asyncio.Future[PreparedPage] = asyncio.get_running_loop().create_future()
        self._waiting.append(((url, response), future))
        self._dispatch()
        return await future

    async def close(self) -> None:
        """Stop all workers, even when a Page or a worker startup has stalled."""
        if self._close_task is None:
            self._closing = True
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self) -> None:
        for _, future in self._waiting:
            future.cancel()
        self._waiting.clear()
        # Replacements already in flight are owned by this close once their starts finish.
        await asyncio.gather(*self._retiring, return_exceptions=True)
        workers = tuple(self._workers)
        try:
            for worker in self._live:
                held = self._busy.get(worker)
                if held is not None and (held.future.cancelled() or self._broken is not None):
                    # The engine has already abandoned this Page.
                    worker.process.kill()
                else:
                    with suppress(OSError):
                        worker.tasks.send(None)
        finally:
            await self._release(workers)

    async def _release(self, workers: tuple[_Worker, ...]) -> None:
        try:
            with self._clock.off_loop():
                await asyncio.to_thread(self._join, workers)
        finally:
            for timer in self._readiness.values():
                timer.cancel()
            for held in self._busy.values():
                held.deadline.cancel()
                held.future.cancel()
            for worker in workers:
                # If the OS refused to end a worker, keep the original cleanup failure.
                with suppress(ValueError):
                    worker.process.close()

    def _join(self, workers: tuple[_Worker, ...]) -> None:
        # The exit budget is shared across workers, including one that sent its last result
        # but is stuck in interpreter shutdown. Page and readiness timers can expire sooner.
        grace = min(_SHUTDOWN_GRACE, max(self._deadline, self._ready_deadline))
        end = monotonic() + grace
        try:
            for worker in workers:
                process = worker.process
                if not wait([process.sentinel], max(0.0, end - monotonic())):
                    process.kill()
            reap_by = monotonic() + _REAP_SECONDS
            for worker in workers:
                _join_process(worker.process, reap_by)
        finally:
            with suppress(OSError):
                self._wake_writer.send(None)
            try:
                if self._waiter is not None:
                    self._waiter.join(_REAP_SECONDS)
                    if self._waiter.is_alive():
                        raise RuntimeError("The parse pool's result waiter did not end.")
            finally:
                for worker in workers:
                    worker.tasks.close()
                    worker.results.close()
                for pipe in (*self._retired, self._wake_reader, self._wake_writer):
                    pipe.close()

    async def _spawn(self) -> None:
        """Starts a worker and hands it the snapshot; the first ones and each replacement."""
        if self._settings is None:
            raise RuntimeError("the parse pool starts a worker before it has its snapshot")
        # Taken before the start is awaited, so replacements started together differ.
        number = self._spawned
        self._spawned += 1
        spawn = multiprocessing.get_context("spawn")
        task_reader, task_writer = spawn.Pipe(duplex=False)
        result_reader, result_writer = spawn.Pipe(duplex=False)
        process = spawn.Process(
            target=_work,
            # Its pipe ends alone: on Windows a child that died while it unpickled the snapshot
            # would leave its result pipe's write end open here (design D1).
            args=(task_reader, result_writer),
            name=f"parse-worker-{number}",
            daemon=True,
        )
        # Starting a spawn process blocks while it pickles its arguments across.
        try:
            with self._clock.off_loop():
                await asyncio.to_thread(process.start)
        except Exception:
            task_writer.close()
            result_reader.close()
            process.close()
            raise
        finally:
            task_reader.close()
            result_writer.close()
        worker = _Worker(process, task_writer, result_reader)
        self._workers.append(worker)
        # Idle only once ready: a Page sent earlier would wait for the worker's start, and its
        # deadline would count that wait (design D8).
        self._live.add(worker)
        with self._watched_lock:
            self._watched[id(result_reader)] = worker
        self._readiness[worker] = asyncio.create_task(
            self._after(self._ready_deadline, self._not_ready, worker)
        )
        if self._started:
            self._wake_writer.send(True)
        # A worker that ended already answers with the end of its result pipe.
        with suppress(OSError):
            task_writer.send(self._settings)

    async def _retire(self, worker: _Worker) -> None:
        """Closes what an ended worker leaves, then starts its replacement (design D3)."""
        name = worker.process.name
        try:
            worker.tasks.close()
            with self._clock.off_loop():
                await asyncio.to_thread(_reap, worker.process)
            self._workers.remove(worker)
        # Its process may still run: a replacement beside it would keep one more for good, and a
        # failure that ended this task unread would leave the waiting Pages waiting for ever.
        except Exception as error:
            failure = WorkerStartError(f"The parse worker {name} that ended could not be released.")
            failure.__cause__ = error
            self._break(failure)
            return
        if self._closing or self._broken is not None:
            return
        try:
            await self._spawn()
        # Starting it failed in this process: the pool cannot keep its workers.
        except Exception as error:
            failure = WorkerStartError("A parse worker could not be started in place of one.")
            failure.__cause__ = error
            self._break(failure)

    def _dispatch(self) -> None:
        """Hands waiting Pages to idle workers, skipping those cancelled while they waited."""
        while self._waiting and self._idle and self._broken is None and not self._closing:
            work, future = self._waiting.popleft()
            if future.done():
                continue
            worker = self._idle.popleft()
            try:
                worker.tasks.send(work)
            # It ended since it last answered, before the waiter saw it.
            except OSError:
                self._waiting.appendleft((work, future))
                self._ended(worker)
                continue
            # From the moment the worker takes it, never from its time in the queue (D8).
            deadline = asyncio.create_task(
                self._after(self._deadline, self._overdue, worker, future)
            )
            self._busy[worker] = _Held(work[0], future, deadline)

    async def _after(self, seconds: float, callback: Callable[..., None], *args: object) -> None:
        await self._clock.sleep(seconds)
        callback(*args)

    def _notify(
        self, loop: asyncio.AbstractEventLoop, callback: Callable[..., None], *args: object
    ) -> None:
        with self._clock.off_loop():
            loop.call_soon_threadsafe(callback, *args)

    def _wait_for_outcomes(self, loop: asyncio.AbstractEventLoop) -> None:
        """The waiter thread: every worker's outcome, handed to the event loop's thread."""
        try:
            self._relay_outcomes(loop)
        # Whatever ends this thread early fails the Pages it would have answered, through their
        # futures, never as a traceback on stderr, which carries JSON lines.
        except BaseException as error:
            broken = RuntimeError("The parse pool's waiter thread failed.")
            broken.__cause__ = error
            with suppress(RuntimeError):
                self._notify(loop, self._break, broken)

    def _relay_outcomes(self, loop: asyncio.AbstractEventLoop) -> None:
        # Until close: a replacement's pipe joins the watched ones at the next wait.
        while True:
            with self._watched_lock:
                watched = dict(self._watched)
                retired, self._retired = self._retired, []
            for end in retired:
                end.close()
            for ready in wait([*(w.results for w in watched.values()), self._wake_reader]):
                if ready is self._wake_reader:
                    if self._wake_reader.recv() is None:
                        return
                    continue
                worker = watched[id(ready)]
                try:
                    message = worker.results.recv_bytes()
                except (EOFError, OSError):
                    # The worker ended: at close, or a crash, whose Page design D3 records.
                    # Already removed if a send to it failed first; closing twice is harmless.
                    with self._watched_lock:
                        self._watched.pop(id(ready), None)
                    worker.results.close()
                    self._notify(loop, self._ended, worker)
                    continue
                if message == _READY:
                    self._notify(loop, self._on_ready, worker)
                elif message.startswith(_START_FAILED):
                    reason = message.removeprefix(_START_FAILED).decode(errors="replace")
                    failure = WorkerStartError(
                        f"The parse worker {worker.process.name} could not start: {reason}"
                    )
                    self._notify(loop, self._break, failure)
                else:
                    self._notify(loop, self._finished, worker, decode_outcome(message))

    def _on_ready(self, worker: _Worker) -> None:
        if worker not in self._live:
            return
        self._ready.add(worker)
        timer = self._readiness.pop(worker, None)
        if timer is not None:
            timer.cancel()
        self._idle.append(worker)
        self._dispatch()

    def _not_ready(self, worker: _Worker) -> None:
        self._readiness.pop(worker, None)
        if worker not in self._live or worker in self._ready:
            return
        name = worker.process.name
        worker.process.kill()
        # Never replaced: a replacement would wait as long (design D1).
        self._break(
            WorkerStartError(
                f"The parse worker {name} was not ready within {self._ready_deadline} s."
            )
        )

    def _overdue(self, worker: _Worker, future: asyncio.Future[PreparedPage]) -> None:
        held = self._busy.get(worker)
        # Its outcome came first; or the pool broke.
        if held is None or held.future is not future:
            return
        del self._busy[worker]
        # An outcome it sent meanwhile finds no Page held and is dropped.
        worker.process.kill()
        if not future.done():
            future.set_result(
                PreparedPage(
                    parse_error="parse_timeout",
                    parse_error_message=f"Preparing {held.url} took more than {self._deadline} "
                    f"s, so its parse worker {worker.process.name} was ended.",
                )
            )
        # Retired and replaced now, never on its end of file: a process that inherited its
        # result pipe would hold that off for as long as it runs (design D8).
        self._ended(worker)

    def _finished(self, worker: _Worker, outcome: Outcome) -> None:
        held = self._busy.pop(worker, None)
        # None once the pool broke, which failed the Page already, or its deadline passed.
        if held is None:
            return
        held.deadline.cancel()
        future = held.future
        # A cancelled Page's outcome only frees its worker.
        if not future.done():
            if isinstance(outcome, BaseException):
                future.set_exception(outcome)
            else:
                future.set_result(outcome)
        self._idle.append(worker)
        self._dispatch()

    def _ended(self, worker: _Worker) -> None:
        if worker not in self._live:
            return
        self._live.discard(worker)
        with suppress(ValueError):
            self._idle.remove(worker)
        self._unwatch(worker)
        name = worker.process.name
        if worker in self._ready:
            self._ready.remove(worker)
        else:
            # It would end the same way again: never replaced (design D1).
            self._break(WorkerStartError(f"The parse worker {name} ended before it was ready."))
        timer = self._readiness.pop(worker, None)
        if timer is not None:
            timer.cancel()
        held = self._busy.pop(worker, None)
        if held is not None:
            held.deadline.cancel()
            if not held.future.done():
                held.future.set_result(
                    crashed_page(f"The parse worker {name} ended while it prepared {held.url}.")
                )
        # close() stops and closes every worker it still lists.
        if self._closing:
            return
        # The Pages waiting meanwhile wait for its replacement (design D3).
        retiring = asyncio.ensure_future(self._retire(worker))
        self._retiring.add(retiring)
        retiring.add_done_callback(self._retiring.discard)

    def _unwatch(self, worker: _Worker) -> None:
        with self._watched_lock:
            # Gone already: the waiter saw its end of file and closed it.
            if self._watched.pop(id(worker.results), None) is None:
                return
            self._retired.append(worker.results)
        # Before its replacement joins them: on Windows before Python 3.13 the waiter's wait
        # takes at most 63 handles (design D1).
        with suppress(OSError):
            self._wake_writer.send(True)

    def _break(self, error: BaseException) -> None:
        """Fails every Page, and every later one: the pool cannot prepare Pages any more."""
        # The first cause counts: a worker that reported its start failure then ends too.
        if self._broken is None:
            self._broken = error
        # Keep active Pages and readiness timers so close still owns their workers.
        futures = [held.future for held in self._busy.values()]
        futures += [future for _, future in self._waiting]
        self._waiting.clear()
        for future in futures:
            if not future.done():
                future.set_exception(self._broken)
