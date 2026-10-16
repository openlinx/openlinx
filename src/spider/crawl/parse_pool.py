"""The pool executor: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import math
import multiprocessing
import os
import signal
import sys
import threading
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from multiprocessing.connection import _ConnectionBase, wait
from multiprocessing.process import BaseProcess
from pathlib import Path, PurePosixPath
from typing import Any

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import PageSettings, PreparedPage, prepare_page
from spider.crawl.parse_wire import Outcome, crashed_page, decode_outcome, encode_outcome
from spider.crawl.urls import NormalizedUrl

# Pages that may wait for a busy worker, per worker (design D2).
BACKLOG_PER_WORKER = 2
# From the moment a worker takes a Page; no flag (design D8). Also how long a worker may take
# to answer ready.
PREPARE_DEADLINE_SECONDS = 30.0
_WINDOWS_WAIT_HANDLES = 63
_CGROUP_ROOT = Path("/sys/fs/cgroup")
_SELF_CGROUP = Path("/proc/self/cgroup")
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


def worker_count(
    *,
    physical: int | None,
    logical: int | None,
    available: int | None,
    quota: int | None,
    limit: int | None,
) -> int:
    """The physical cores available less two, for the crawl process and the writer (design D1)."""
    cores = physical or (logical or 0) // 2
    if available and logical and available < logical:
        # Only part of the machine is ours (taskset, a container's cpuset): as many physical
        # cores as its share of the logical ones.
        cores = cores * available // logical
    if quota is not None:
        # CPU time, however the cores share it out (docker --cpus, a Kubernetes limit).
        cores = min(cores, quota)
    workers = max(1, cores - 2)
    return workers if limit is None else min(workers, limit)


def cpu_quota(root: Path, membership: Path) -> int | None:
    """The CPUs a cgroup v2 quota (`cpu.max`) leaves this process, the lowest up to the root."""
    try:
        lines = membership.read_text().splitlines()
    except OSError:
        return None
    # cgroup v2's own line; v1's controllers have lines of their own, which are not read.
    group = next((PurePosixPath(line[3:]) for line in lines if line.startswith("0::")), None)
    if group is None:
        return None
    quotas: list[int] = []
    for path in (group, *group.parents):
        try:
            limit, period = root.joinpath(*path.parts[1:], "cpu.max").read_text().split()
            if limit != "max":
                quotas.append(math.ceil(int(limit) / int(period)))
        except (OSError, ValueError):
            continue
    return min(quotas, default=None)


def worker_limit(platform: str, version: tuple[int, int]) -> int | None:
    """The most workers the waiter thread can watch, or None for no limit (design D1)."""
    # connection.wait takes at most 63 handles on Windows before Python 3.13, and the waiter
    # watches one per worker, its result pipe, and its own wake pipe.
    if platform == "win32" and version < (3, 13):
        return _WINDOWS_WAIT_HANDLES - 1
    return None


def default_workers() -> int:
    # Imported here: psutil stays off the CLI's startup path (design D1).
    import psutil

    return worker_count(
        physical=psutil.cpu_count(logical=False),
        logical=os.cpu_count(),
        available=_available_cpus(psutil.Process()),
        quota=cpu_quota(_CGROUP_ROOT, _SELF_CGROUP),
        limit=_waiter_limit(),
    )


def _waiter_limit() -> int | None:
    return worker_limit(sys.platform, (sys.version_info.major, sys.version_info.minor))


def _available_cpus(process: Any) -> int | None:
    """The logical CPUs this process may run on: Python 3.13 says, before it psutil does."""
    process_cpu_count = getattr(os, "process_cpu_count", None)
    if process_cpu_count is not None:
        count: int | None = process_cpu_count()
        return count
    # macOS has no affinity.
    affinity = getattr(process, "cpu_affinity", None)
    return None if affinity is None else len(affinity())


def _reap(process: BaseProcess) -> None:
    # Killed first, so that the join is bounded: an ended worker may still be exiting.
    process.kill()
    process.join()
    process.close()


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
    deadline: asyncio.TimerHandle


class PoolExecutor:
    """Prepares each Page in one of `workers` spawn processes, one Page per worker at a time."""

    def __init__(
        self,
        workers: int | None = None,
        deadline: float = PREPARE_DEADLINE_SECONDS,
        ready_deadline: float = PREPARE_DEADLINE_SECONDS,
    ) -> None:
        self.workers = default_workers() if workers is None else workers
        limit = _waiter_limit()
        if self.workers < 1 or (limit is not None and self.workers > limit):
            raise ValueError(
                f"{self.workers} parse workers: the pool runs at least 1"
                + ("" if limit is None else f" and at most {limit} here")
            )
        self.backlog = BACKLOG_PER_WORKER * self.workers
        self._deadline = deadline
        self._ready_deadline = ready_deadline
        self._settings: PageSettings | None = None
        # The workers not yet retired, and those still running, idle or busy, or ready; a
        # worker that ended is retired, so a long hostile Crawl keeps no pipe or process of
        # it. The count and the process ids of every worker started.
        self._workers: list[_Worker] = []
        self._spawned = 0
        self._pids: list[int] = []
        self._live: set[_Worker] = set()
        self._ready: set[_Worker] = set()
        self._idle: deque[_Worker] = deque()
        # The Page each busy worker holds, and the timer of its deadline (design D8).
        self._busy: dict[_Worker, _Held] = {}
        # The timer of each worker's ready answer.
        self._readiness: dict[_Worker, asyncio.TimerHandle] = {}
        self._waiting: deque[tuple[_Work, asyncio.Future[PreparedPage]]] = deque()
        # Each ended worker's retirement, which starts its replacement.
        self._retiring: set[asyncio.Task[None]] = set()
        self._started = False
        self._closing = False
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

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(self._pids)

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings
        for _ in range(self.workers):
            await self._spawn()
        # A daemon: nothing it waits for may keep the crawl process from exiting.
        self._waiter = threading.Thread(
            target=self._wait_for_outcomes,
            args=(asyncio.get_running_loop(),),
            name="spider-parse-waiter",
            daemon=True,
        )
        self._waiter.start()
        self._started = True

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        if not self._started:
            raise RuntimeError("the parse pool prepares a Page before it is started")
        if self._broken is not None:
            raise self._broken
        future: asyncio.Future[PreparedPage] = asyncio.get_running_loop().create_future()
        self._waiting.append(((url, response), future))
        self._dispatch()
        return await future

    async def close(self) -> None:
        self._closing = True
        # Nothing waits any more at a normal end; a stop leaves no Page for a worker.
        for _, future in self._waiting:
            future.cancel()
        self._waiting.clear()
        # A replacement still starting is stopped with the others once it has started.
        await asyncio.gather(*self._retiring, return_exceptions=True)
        # Only now: a replacement that has just started armed a readiness timer.
        timers = [*self._readiness.values(), *(held.deadline for held in self._busy.values())]
        for timer in timers:
            timer.cancel()
        for worker in self._live:
            # A worker that ended meanwhile has nothing to stop.
            with suppress(OSError):
                worker.tasks.send(None)
        await asyncio.to_thread(self._join, list(self._workers))

    def _join(self, workers: list[_Worker]) -> None:
        try:
            for worker in workers:
                worker.process.join()
        finally:
            with suppress(OSError):
                self._wake_writer.send(None)
            if self._waiter is not None:
                self._waiter.join()
            ends = [worker.tasks for worker in workers]
            ends += [worker.results for worker in workers]
            for end in (*ends, *self._retired, self._wake_reader, self._wake_writer):
                end.close()

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
            name=f"spider-parse-{number}",
            daemon=True,
        )
        # Starting a spawn process blocks while it pickles its arguments across.
        await asyncio.to_thread(process.start)
        task_reader.close()
        result_writer.close()
        worker = _Worker(process, task_writer, result_reader)
        self._workers.append(worker)
        if process.pid is not None:
            self._pids.append(process.pid)
        # Idle only once ready: a Page sent earlier would wait for the worker's start, and its
        # deadline would count that wait (design D8).
        self._live.add(worker)
        with self._watched_lock:
            self._watched[id(result_reader)] = worker
        self._readiness[worker] = asyncio.get_running_loop().call_later(
            self._ready_deadline, self._not_ready, worker
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
            await asyncio.to_thread(_reap, worker.process)
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
        while self._waiting and self._idle and self._broken is None:
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
            deadline = asyncio.get_running_loop().call_later(
                self._deadline, self._overdue, worker, future
            )
            self._busy[worker] = _Held(work[0], future, deadline)

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
                loop.call_soon_threadsafe(self._break, broken)

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
                    loop.call_soon_threadsafe(self._ended, worker)
                    continue
                if message == _READY:
                    loop.call_soon_threadsafe(self._on_ready, worker)
                elif message.startswith(_START_FAILED):
                    reason = message.removeprefix(_START_FAILED).decode(errors="replace")
                    failure = WorkerStartError(
                        f"The parse worker {worker.process.name} could not start: {reason}"
                    )
                    loop.call_soon_threadsafe(self._break, failure)
                else:
                    loop.call_soon_threadsafe(self._finished, worker, decode_outcome(message))

    def _on_ready(self, worker: _Worker) -> None:
        self._ready.add(worker)
        timer = self._readiness.pop(worker, None)
        if timer is not None:
            timer.cancel()
        if worker in self._live:
            self._idle.append(worker)
            self._dispatch()

    def _not_ready(self, worker: _Worker) -> None:
        self._readiness.pop(worker, None)
        if worker not in self._live or worker in self._ready or self._closing:
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
        if worker not in self._ready:
            # It would end the same way again: never replaced (design D1).
            self._break(WorkerStartError(f"The parse worker {name} ended before it was ready."))
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
        self._workers.remove(worker)
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
        # The readiness timers stay: each still ends a worker that is never ready.
        for held in self._busy.values():
            held.deadline.cancel()
        futures = [held.future for held in self._busy.values()]
        futures += [future for _, future in self._waiting]
        self._busy.clear()
        self._waiting.clear()
        for future in futures:
            if not future.done():
                future.set_exception(self._broken)
