"""Verify physical exit when another process keeps the worker's descriptor open."""

import asyncio
import os
import sys
import threading
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

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


class _Options(msgspec.Struct, frozen=True):
    folder: Path


class _WorkerId(msgspec.Struct, frozen=True):
    pid: int


def _pid(tree: LexborHTMLParser, page: PageInput, config: _Options) -> _WorkerId:
    if sys.platform != "win32" and page.url.endswith("/held"):
        child = os.fork()
        if child == 0:
            threading.Event().wait(15)
            os._exit(0)
        (config.folder / "holder").write_text(str(child), encoding="ascii")
        threading.Event().wait(15)
    return _WorkerId(os.getpid())


@pytest.mark.skipif(sys.platform == "win32", reason="Fork inherits the worker's descriptors")
async def test_a_worker_over_its_deadline_is_replaced_while_a_child_holds_its_pipe(
    tmp_path: Path,
) -> None:
    hook = extractor("worker_id", _pid, _Options(tmp_path))
    pool = PoolExecutor(1, deadline=1)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    holder: psutil.Process | None = None
    try:
        was = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 10)
        first = hook.output(dict(was.outputs))
        assert first is not None
        failed = await asyncio.wait_for(
            pool.prepare(NormalizedUrl("http://127.0.0.1/held"), _RESPONSE), 10
        )
        assert failed.parse_error == "parse_timeout"
        holder = psutil.Process(int((tmp_path / "holder").read_text(encoding="ascii")))
        holder.create_time()
        prepared = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 3)
        after = hook.output(dict(prepared.outputs))
        assert after is not None
        assert after.pid != first.pid
        assert holder.is_running()
    finally:
        if holder is not None:
            with suppress(psutil.NoSuchProcess):
                holder.kill()
        await asyncio.wait_for(pool.close(), 10)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX waitpid can reap the pool's child")
async def test_close_accepts_a_worker_already_reaped_by_the_owner(tmp_path: Path) -> None:
    hook = extractor("worker_id", _pid, _Options(tmp_path))
    pool = PoolExecutor(1, deadline=1, ready_deadline=2)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    try:
        prepared = await asyncio.wait_for(pool.prepare(_URL, _RESPONSE), 6)
        output = hook.output(dict(prepared.outputs))
        assert output is not None
        psutil.Process(output.pid).kill()
        # The event loop cannot retire the worker before this waitpid consumes its status.
        assert os.waitpid(output.pid, 0)[0] == output.pid  # noqa: ASYNC222
    finally:
        await pool.close()
