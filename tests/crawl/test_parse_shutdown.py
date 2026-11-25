"""Check timeout and stop behavior using real spawned workers."""

import asyncio
import multiprocessing
import os
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

import msgspec
import psutil
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.parse_pool import PoolExecutor, WorkerStartError
from openlinx.crawl.pages.preparation import PageInput, PageSettings, extractor
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl

_URL = NormalizedUrl("http://127.0.0.1/")
_RESPONSE = FetchResult(
    status_code=200,
    reason="OK",
    headers=(("Content-Type", "text/html"),),
    body=b"<p>Page</p>",
    fetched_at=datetime(2026, 11, 25, tzinfo=UTC),
    response_time_ms=0,
)


class _WorkerId(msgspec.Struct, frozen=True):
    pid: int


class _Block(msgspec.Struct, frozen=True):
    folder: Path
    before_ready: bool = False

    def __post_init__(self) -> None:
        if self.before_ready and multiprocessing.parent_process() is not None:
            _block_here(self.folder)


def _block_here(folder: Path) -> None:
    (folder / str(os.getpid())).touch()
    # Keep a failed assertion diagnosable even if the test's emergency kill fails.
    threading.Event().wait(90)


def _hold(tree: LexborHTMLParser, page: PageInput, config: _Block) -> _WorkerId:
    _block_here(config.folder)
    return _WorkerId(os.getpid())


def _hold_exit(tree: LexborHTMLParser, page: PageInput, config: _Block) -> _WorkerId:
    # A non-daemon thread leaves the worker stuck at interpreter shutdown after the outcome.
    blocker = threading.Thread(target=threading.Event().wait, args=(90,), daemon=False)
    blocker.start()
    return _WorkerId(os.getpid())


def _settings(config: _Block) -> PageSettings:
    return PageSettings(
        scope=scope_rules(_URL),
        extractors=(extractor("holding", _hold, config),),
        strip_params=None,
    )


def _observe_workers(folder: Path, count: int) -> list[psutil.Process]:
    deadline = monotonic() + 8
    while monotonic() < deadline:
        marks = list(folder.iterdir())
        if len(marks) == count:
            workers = [psutil.Process(int(mark.name)) for mark in marks]
            for worker in workers:
                worker.create_time()
            return workers
        sleep(0.01)
    raise AssertionError(f"{count} workers did not enter the blocking operation")


async def _close_within(pool: PoolExecutor, workers: list[psutil.Process], seconds: float) -> None:
    ending = asyncio.create_task(pool.close())
    try:
        await asyncio.wait_for(asyncio.shield(ending), seconds)
        assert [worker.pid for worker in workers if worker.is_running()] == []
    finally:
        # Release only the observed workers if the assertion failed before the pool could reap.
        for worker in workers:
            with suppress(psutil.NoSuchProcess):
                worker.kill()
        await asyncio.wait_for(ending, 10)


async def test_close_ends_hung_work_after_the_caller_cancels(tmp_path: Path) -> None:
    folder = tmp_path / "workers"
    folder.mkdir()
    pool = PoolExecutor(1)
    await pool.start(_settings(_Block(folder)))
    pending = asyncio.create_task(pool.prepare(_URL, _RESPONSE))
    workers: list[psutil.Process] = []
    try:
        workers = await asyncio.to_thread(_observe_workers, folder, 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    finally:
        await _close_within(pool, workers, 4)


async def test_close_keeps_the_other_workers_readiness_deadline_after_failure(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "workers"
    folder.mkdir()
    pool = PoolExecutor(2, ready_deadline=6)
    await pool.start(_settings(_Block(folder, before_ready=True)))
    workers: list[psutil.Process] = []
    try:
        workers = await asyncio.to_thread(_observe_workers, folder, 2)
        workers[0].kill()
        with pytest.raises(WorkerStartError, match="ended before it was ready"):
            await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 3)
        assert workers[1].is_running()
    finally:
        await _close_within(pool, workers, 8)


async def test_close_bounds_a_worker_blocked_after_its_last_outcome(tmp_path: Path) -> None:
    hook = extractor("held_exit", _hold_exit, _Block(tmp_path))
    pool = PoolExecutor(1, deadline=2, ready_deadline=3)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    workers: list[psutil.Process] = []
    try:
        prepared = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 5)
        output = hook.output(dict(prepared.outputs))
        assert output is not None
        worker = psutil.Process(output.pid)
        worker.create_time()
        workers = [worker]
    finally:
        await _close_within(pool, workers, 5)
