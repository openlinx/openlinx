"""The pool executor: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import multiprocessing
import os
import signal
import sys
import threading
from collections import deque
from dataclasses import dataclass
from multiprocessing.connection import _ConnectionBase, wait
from multiprocessing.process import BaseProcess
from typing import Any

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import PageSettings, PreparedPage, prepare_page
from spider.crawl.urls import NormalizedUrl

# Pages that may wait for a busy worker, per worker (design D2).
BACKLOG_PER_WORKER = 2

# A Connection on POSIX, a PipeConnection on Windows: the one class both pipe ends share.
type _PipeEnd = _ConnectionBase[Any, Any]
type _Work = tuple[NormalizedUrl, FetchResult]
# The PreparedPage, or the exception prepare_page raised, which in-process reaches the engine.
type _Outcome = PreparedPage | BaseException


def _work(settings: PageSettings, tasks: _PipeEnd, results: _PipeEnd) -> None:
    """A worker's life; the snapshot is a start argument, so it is pickled once (design D1)."""
    # Ctrl+C reaches every process of a console: the crawl process ends its workers in order.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    while (work := tasks.recv()) is not None:
        url, response = work
        outcome: _Outcome
        try:
            outcome = prepare_page(url, response, settings)
        except Exception as error:
            outcome = error
        results.send(outcome)


def worker_count(*, physical: int | None, logical: int | None, available: int | None) -> int:
    """Physical cores less two, for the crawl process and the writer (design D1)."""
    cores = physical or (logical or 0) // 2
    if available:
        # A container's CPU limit, which only Python 3.13's os.process_cpu_count reports.
        cores = min(cores, available)
    return max(1, cores - 2)


def default_workers() -> int:
    # Imported here: psutil stays off the CLI's startup path (design D1).
    import psutil

    return worker_count(
        physical=psutil.cpu_count(logical=False),
        logical=os.cpu_count(),
        available=getattr(os, "process_cpu_count", os.cpu_count)(),
    )


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
        self._count = default_workers() if workers is None else workers
        self.workers = self._count
        self.backlog = BACKLOG_PER_WORKER * self._count
        self._workers: list[_Worker] = []
        self._idle: deque[_Worker] = deque()
        # The Page each busy worker holds.
        self._busy: dict[_Worker, asyncio.Future[PreparedPage]] = {}
        self._waiting: deque[tuple[_Work, asyncio.Future[PreparedPage]]] = deque()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiter: threading.Thread | None = None
        self._wake_reader, self._wake_writer = multiprocessing.Pipe(duplex=False)
        self._broken: RuntimeError | None = None

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(worker.process.pid for worker in self._workers if worker.process.pid)

    async def start(self, settings: PageSettings) -> None:
        self._loop = asyncio.get_running_loop()
        spawn = multiprocessing.get_context("spawn")
        for n in range(self._count):
            task_reader, task_writer = spawn.Pipe(duplex=False)
            result_reader, result_writer = spawn.Pipe(duplex=False)
            process = spawn.Process(
                target=_work,
                args=(settings, task_reader, result_writer),
                name=f"spider-parse-{n}",
                daemon=True,
            )
            # Starting a spawn process blocks while it pickles its arguments across.
            await asyncio.to_thread(process.start)
            task_reader.close()
            result_writer.close()
            worker = _Worker(process, task_writer, result_reader)
            self._workers.append(worker)
            self._idle.append(worker)
        self._waiter = threading.Thread(
            target=self._wait_for_outcomes, args=(self._loop,), name="spider-parse-waiter"
        )
        self._waiter.start()

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        if self._broken is not None:
            raise self._broken
        future: asyncio.Future[PreparedPage] = asyncio.get_running_loop().create_future()
        if self._idle:
            self._hand(self._idle.popleft(), (url, response), future)
        else:
            self._waiting.append(((url, response), future))
        return await future

    async def close(self) -> None:
        for worker in self._workers:
            worker.tasks.send(None)
        await asyncio.to_thread(self._join)

    def _join(self) -> None:
        for worker in self._workers:
            worker.process.join()
        self._wake_writer.send(None)
        if self._waiter is not None:
            self._waiter.join()
        for worker in self._workers:
            worker.tasks.close()
            worker.results.close()
        self._wake_reader.close()
        self._wake_writer.close()

    def _hand(self, worker: _Worker, work: _Work, future: asyncio.Future[PreparedPage]) -> None:
        self._busy[worker] = future
        worker.tasks.send(work)

    def _wait_for_outcomes(self, loop: asyncio.AbstractEventLoop) -> None:
        """The waiter thread: every worker's outcome, handed to the event loop's thread."""
        try:
            self._relay_outcomes(loop)
        # Whatever ends this thread early must fail the Pages it would have answered, never
        # leave them waiting.
        except BaseException as error:
            loop.call_soon_threadsafe(self._fail_all, error)
            raise

    def _relay_outcomes(self, loop: asyncio.AbstractEventLoop) -> None:
        # By identity: on Windows a pipe end is a PipeConnection, which is no Connection.
        pending = {id(worker.results): worker for worker in self._workers}
        while pending:
            for ready in wait([*(w.results for w in pending.values()), self._wake_reader]):
                if ready is self._wake_reader:
                    return
                worker = pending[id(ready)]
                outcome: _Outcome
                try:
                    outcome = worker.results.recv()
                except EOFError:
                    # The worker ended: at close, or a crash, which design D3 handles.
                    del pending[id(ready)]
                    continue
                # An outcome this process cannot unpickle, such as an extractor's output whose
                # class cannot be rebuilt here, is that one Page's failure, never the pool's.
                except Exception as error:
                    outcome = error
                loop.call_soon_threadsafe(self._finished, worker, outcome)

    def _fail_all(self, error: BaseException) -> None:
        self._broken = RuntimeError("The parse pool's waiter thread failed.")
        self._broken.__cause__ = error
        futures = [*self._busy.values(), *(future for _, future in self._waiting)]
        self._busy.clear()
        self._waiting.clear()
        for future in futures:
            if not future.done():
                future.set_exception(self._broken)

    def _finished(self, worker: _Worker, outcome: _Outcome) -> None:
        future = self._busy.pop(worker, None)
        # A cancelled Page's outcome only frees its worker.
        if future is not None and not future.done():
            if isinstance(outcome, BaseException):
                future.set_exception(outcome)
            else:
                future.set_result(outcome)
        if self._waiting:
            work, waiting = self._waiting.popleft()
            self._hand(worker, work, waiting)
        else:
            self._idle.append(worker)
