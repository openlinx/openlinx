"""A blocked worker transport must not stop the Crawl event loop."""

import asyncio
import os
import sys
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import msgspec
import psutil
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.parse_pool import PoolExecutor
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


def _pid(tree: LexborHTMLParser, page: PageInput, config: None) -> _WorkerId:
    return _WorkerId(os.getpid())


async def test_a_blocked_work_transfer_does_not_hold_the_loop() -> None:
    hook = extractor("worker_id", _pid, None)
    pool = PoolExecutor(1)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    try:
        first = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 10)
        output = hook.output(dict(first.outputs))
        assert output is not None
        worker = psutil.Process(output.pid)
        worker.create_time()
        worker.suspend()
        # If the loop is wedged, release it independently and record the missed bound.
        emergency = threading.Timer(6, worker.kill)
        emergency.start()
        try:
            start = monotonic()
            pending = asyncio.create_task(
                pool.prepare(_URL, replace(_RESPONSE, body=b"x" * (2 * 1024 * 1024)))
            )
            # Give the sender a turn after prepare schedules the I/O.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not pending.done()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert monotonic() - start < 3
            await asyncio.wait_for(pool.close(), 3)
            assert not worker.is_running()
        finally:
            emergency.cancel()
            with suppress(psutil.NoSuchProcess):
                worker.kill()
    finally:
        await asyncio.wait_for(pool.close(), 10)


async def test_a_worker_stalled_before_taking_a_page_is_replaced() -> None:
    await _replace_stalled_worker()


@pytest.mark.skipif(sys.platform != "linux", reason="The Linux boot time comes from /proc/stat")
async def test_replacement_reaches_ready_after_linux_boot_time_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    procfs = tmp_path / "proc"
    procfs.mkdir()
    owner = str(os.getpid())
    (procfs / owner).symlink_to(Path("/proc") / owner, target_is_directory=True)
    (tmp_path / "sitecustomize.py").write_text(
        """
import os
from pathlib import Path

procfs = Path(__file__).with_name("proc")
if (procfs / "stat").exists():
    import psutil

    psutil.PROCFS_PATH = str(procfs)
    (procfs / "observed").write_text(
        f"{os.getpid()} {int(psutil.boot_time())}", encoding="ascii"
    )
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path), prepend=os.pathsep)

    shifted_boot = 0

    def step_clock() -> None:
        nonlocal shifted_boot
        # Both workers look up the same real owner PID and unchanged start ticks.
        shifted_boot = int(psutil.boot_time()) + 1
        (procfs / "stat").write_text(f"btime {shifted_boot}\n", encoding="ascii")

    replacement = await _replace_stalled_worker(step_clock)
    assert (procfs / "observed").read_text(encoding="ascii") == f"{replacement} {shifted_boot}"


async def _replace_stalled_worker(before_suspend: Callable[[], None] | None = None) -> int:
    hook = extractor("worker_id", _pid, None)
    pool = PoolExecutor(1, deadline=2)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    worker: psutil.Process | None = None
    try:
        first = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 10)
        identity = hook.output(dict(first.outputs))
        assert identity is not None
        worker = psutil.Process(identity.pid)
        worker.create_time()
        if before_suspend is not None:
            before_suspend()
        worker.suspend()

        undelivered = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 5)
        assert undelivered.parse_error == "worker_crashed"
        following = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 8)
        replacement = hook.output(dict(following.outputs))
        assert replacement is not None
        assert replacement.pid != identity.pid
        assert not worker.is_running()
        return replacement.pid
    finally:
        if worker is not None:
            with suppress(psutil.NoSuchProcess):
                worker.resume()
        await asyncio.wait_for(pool.close(), 10)
