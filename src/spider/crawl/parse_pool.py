"""The pool executor: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import math
import multiprocessing
import os
import pickle
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

import msgspec

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import PageSettings, PreparedPage, prepare_page
from spider.crawl.urls import NormalizedUrl

# Pages that may wait for a busy worker, per worker (design D2).
BACKLOG_PER_WORKER = 2
_WINDOWS_WAIT_HANDLES = 63
_CGROUP_ROOT = Path("/sys/fs/cgroup")
_SELF_CGROUP = Path("/proc/self/cgroup")
# A worker's first answer; an outcome is a pickle, which never starts with these bytes.
_READY = b"ready"
_START_FAILED = b"failed:"

# A Connection on POSIX, a PipeConnection on Windows: the one class both pipe ends share.
type _PipeEnd = _ConnectionBase[Any, Any]
type _Work = tuple[NormalizedUrl, FetchResult]
# The PreparedPage, or the exception prepare_page raised, which in-process reaches the engine.
type _Outcome = PreparedPage | BaseException
# What crosses for a PreparedPage: the Page without its outputs, and each output's pickle.
type _Sent = tuple[PreparedPage, tuple[tuple[str, bytes], ...]]


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
        outcome: _Outcome
        try:
            outcome = prepare_page(url, response, settings)
        except Exception as error:
            outcome = error
        try:
            results.send_bytes(_pickled(outcome))
        # As at recv: the crawl process ended while this worker prepared its Page.
        except OSError:
            return


def _pickled(outcome: _Outcome) -> bytes:
    """What a worker sends: whatever cannot cross to the crawl process costs only itself."""
    if isinstance(outcome, PreparedPage):
        with suppress(Exception):
            return pickle.dumps(_sendable(outcome), pickle.HIGHEST_PROTOCOL)
        return pickle.dumps(RuntimeError("The parse worker could not send its PreparedPage."))
    with suppress(Exception):
        return pickle.dumps(outcome, pickle.HIGHEST_PROTOCOL)
    return pickle.dumps(RuntimeError(f"{type(outcome).__name__}: {outcome}"))


def _sendable(page: PreparedPage) -> _Sent:
    """The Page without its outputs, and each output pickled by itself (design D3)."""
    outputs: list[tuple[str, bytes]] = []
    failures: list[str] = []
    for name, output in page.outputs:
        try:
            outputs.append((name, pickle.dumps(output, pickle.HIGHEST_PROTOCOL)))
        except Exception as error:
            failures.append(f"{name}: {type(error).__name__}")
    return _with_failures(page, failures, ()), tuple(outputs)


def _outcome(message: bytes) -> _Outcome:
    try:
        return _received(message)
    # A Page whose own record this process cannot read is that one Page's failure (design D3).
    except Exception as error:
        return _crashed(
            "The Page's record from its parse worker could not be read: "
            f"{type(error).__name__}: {error}"
        )


def _crashed(message: str) -> PreparedPage:
    """Nothing came out of the Page's preparation: 020 records it with parsed = 0."""
    return PreparedPage(parse_error="worker_crashed", parse_error_message=message)


def _received(message: bytes) -> _Outcome:
    # From our own worker over a pipe of its own, as multiprocessing's recv() would unpickle it.
    sent: _Sent | BaseException = pickle.loads(message)  # noqa: S301
    if isinstance(sent, BaseException):
        return sent
    page, outputs = sent
    kept: list[tuple[str, msgspec.Struct]] = []
    failures: list[str] = []
    for name, data in outputs:
        try:
            kept.append((name, pickle.loads(data)))  # noqa: S301
        # Such as an output whose class cannot be rebuilt in this process.
        except Exception as error:
            failures.append(f"{name}: {type(error).__name__}")
    return _with_failures(page, failures, tuple(kept))


def _with_failures(
    page: PreparedPage, failures: list[str], outputs: tuple[tuple[str, Any], ...]
) -> PreparedPage:
    """In process an output would reach its handler; one that cannot cross fails as its
    extractor would (020 D16), and the Page keeps its Links."""
    if not failures:
        return msgspec.structs.replace(page, outputs=outputs)
    messages = [page.parse_error_message] if page.parse_error_message else []
    return msgspec.structs.replace(
        page,
        outputs=outputs,
        parse_error="extractor_error",
        parse_error_message="; ".join([*messages, *failures]),
    )


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


@dataclass(frozen=True, eq=False)
class _Worker:
    process: BaseProcess
    # The crawl process writes work to one pipe and reads outcomes from the other, so the event
    # loop's sends and the waiter thread's receives never share a connection.
    tasks: _PipeEnd
    results: _PipeEnd


class PoolExecutor:
    """Prepares each Page in one of `workers` spawn processes, one Page per worker at a time."""

    def __init__(self, workers: int | None = None) -> None:
        self.workers = default_workers() if workers is None else workers
        limit = _waiter_limit()
        if self.workers < 1 or (limit is not None and self.workers > limit):
            raise ValueError(
                f"{self.workers} parse workers: the pool runs at least 1"
                + ("" if limit is None else f" and at most {limit} here")
            )
        self.backlog = BACKLOG_PER_WORKER * self.workers
        self._settings: PageSettings | None = None
        # Every worker started, and those still running, idle or busy, or ready.
        self._workers: list[_Worker] = []
        self._live: set[_Worker] = set()
        self._ready: set[_Worker] = set()
        self._idle: deque[_Worker] = deque()
        # The Page each busy worker holds: its URL and its future.
        self._busy: dict[_Worker, tuple[NormalizedUrl, asyncio.Future[PreparedPage]]] = {}
        self._waiting: deque[tuple[_Work, asyncio.Future[PreparedPage]]] = deque()
        self._replacing: set[asyncio.Task[None]] = set()
        self._started = False
        self._closing = False
        self._broken: BaseException | None = None
        # The result pipes the waiter thread reads, by identity: on Windows a pipe end is a
        # PipeConnection, which is no Connection. The waiter reads it; the loop's thread adds.
        self._watched: dict[int, _Worker] = {}
        self._watched_lock = threading.Lock()
        self._waiter: threading.Thread | None = None
        # True: watch the pipes again, for a replacement; None: stop.
        self._wake_reader, self._wake_writer = multiprocessing.Pipe(duplex=False)

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(worker.process.pid for worker in self._workers if worker.process.pid)

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
        await asyncio.gather(*self._replacing, return_exceptions=True)
        for worker in self._live:
            # A worker that ended meanwhile has nothing to stop.
            with suppress(OSError):
                worker.tasks.send(None)
        await asyncio.to_thread(self._join)

    def _join(self) -> None:
        try:
            for worker in self._workers:
                worker.process.join()
        finally:
            with suppress(OSError):
                self._wake_writer.send(None)
            if self._waiter is not None:
                self._waiter.join()
            ends = [worker.tasks for worker in self._workers]
            ends += [worker.results for worker in self._workers]
            for end in (*ends, self._wake_reader, self._wake_writer):
                end.close()

    async def _spawn(self) -> None:
        """Starts a worker and hands it the snapshot; the first ones and each replacement."""
        if self._settings is None:
            raise RuntimeError("the parse pool starts a worker before it has its snapshot")
        spawn = multiprocessing.get_context("spawn")
        task_reader, task_writer = spawn.Pipe(duplex=False)
        result_reader, result_writer = spawn.Pipe(duplex=False)
        process = spawn.Process(
            target=_work,
            # Its pipe ends alone: on Windows a child that died while it unpickled the snapshot
            # would leave its result pipe's write end open here (design D1).
            args=(task_reader, result_writer),
            name=f"spider-parse-{len(self._workers)}",
            daemon=True,
        )
        # Starting a spawn process blocks while it pickles its arguments across.
        await asyncio.to_thread(process.start)
        task_reader.close()
        result_writer.close()
        worker = _Worker(process, task_writer, result_reader)
        self._workers.append(worker)
        self._live.add(worker)
        self._idle.append(worker)
        with self._watched_lock:
            self._watched[id(result_reader)] = worker
        if self._started:
            self._wake_writer.send(True)
        # A worker that ended already answers with the end of its result pipe.
        with suppress(OSError):
            task_writer.send(self._settings)
        self._dispatch()

    async def _replace(self) -> None:
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
            self._busy[worker] = (work[0], future)

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
                    with self._watched_lock:
                        del self._watched[id(ready)]
                    loop.call_soon_threadsafe(self._ended, worker)
                    continue
                if message == _READY:
                    loop.call_soon_threadsafe(self._ready.add, worker)
                elif message.startswith(_START_FAILED):
                    reason = message.removeprefix(_START_FAILED).decode(errors="replace")
                    failure = WorkerStartError(
                        f"The parse worker {worker.process.name} could not start: {reason}"
                    )
                    loop.call_soon_threadsafe(self._break, failure)
                else:
                    loop.call_soon_threadsafe(self._finished, worker, _outcome(message))

    def _finished(self, worker: _Worker, outcome: _Outcome) -> None:
        held = self._busy.pop(worker, None)
        # None once the pool broke, which failed the Page already.
        if held is None:
            return
        _, future = held
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
        if worker not in self._ready:
            # It would end the same way again: never replaced (design D1).
            name = worker.process.name
            self._break(WorkerStartError(f"The parse worker {name} ended before it was ready."))
            return
        held = self._busy.pop(worker, None)
        if held is not None:
            _, future = held
            if not future.done():
                future.set_result(_crashed(f"The parse worker {worker.process.name} ended."))
        if self._closing or self._broken is not None:
            return
        # The Pages waiting meanwhile wait for it (design D3).
        replacement = asyncio.ensure_future(self._replace())
        self._replacing.add(replacement)
        replacement.add_done_callback(self._replacing.discard)

    def _break(self, error: BaseException) -> None:
        """Fails every Page, and every later one: the pool cannot prepare Pages any more."""
        # The first cause counts: a worker that reported its start failure then ends too.
        if self._broken is None:
            self._broken = error
        futures = [future for _, future in self._busy.values()]
        futures += [future for _, future in self._waiting]
        self._busy.clear()
        self._waiting.clear()
        for future in futures:
            if not future.done():
                future.set_exception(self._broken)
