"""Verify ownership when a caller cancels while the OS is starting a worker."""

import asyncio
import threading
from contextlib import suppress
from multiprocessing.process import BaseProcess

import psutil
import pytest

from openlinx.crawl.pages.parse_pool import PoolExecutor
from openlinx.crawl.pages.preparation import PageSettings
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl


async def test_cancelling_start_keeps_the_spawned_worker_owned_until_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: asyncio.Queue[psutil.Process] = asyncio.Queue()
    release_spawn = threading.Event()
    loop = asyncio.get_running_loop()
    spawn = BaseProcess.start

    def start(process: BaseProcess) -> None:
        spawn(process)
        if process.name == "parse-worker-0":
            assert process.pid is not None
            child = psutil.Process(process.pid)
            child.create_time()
            loop.call_soon_threadsafe(started.put_nowait, child)
            if not release_spawn.wait(8):
                raise RuntimeError("The test did not release the process-spawn boundary.")

    monkeypatch.setattr(BaseProcess, "start", start)
    url = NormalizedUrl("http://127.0.0.1/")
    pool = PoolExecutor(1)
    opening = asyncio.create_task(
        pool.start(PageSettings(scope=scope_rules(url), extractors=(), strip_params=None))
    )
    child = await asyncio.wait_for(started.get(), 8)
    closing: asyncio.Task[None] | None = None
    try:
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening
        assert child.is_running()
        closing = asyncio.create_task(pool.close())
        # Keep the OS boundary paused while close has an opportunity to return early.
        done, _ = await asyncio.wait({closing}, timeout=0.3)
        assert not done, "close returned before it took ownership of the worker"
        release_spawn.set()
        await asyncio.wait_for(asyncio.shield(closing), 5)
        assert not child.is_running()
    finally:
        release_spawn.set()
        with suppress(psutil.NoSuchProcess):
            child.kill()
        if closing is not None:
            await asyncio.wait_for(closing, 10)
