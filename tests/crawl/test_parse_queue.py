"""A canceled queued Page never reaches a spawn worker."""

import asyncio
import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

import msgspec
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


class _Trace(msgspec.Struct, frozen=True):
    folder: Path


class _WorkerId(msgspec.Struct, frozen=True):
    pid: int


def _track(tree: LexborHTMLParser, page: PageInput, config: _Trace) -> _WorkerId:
    name = page.url.rsplit("/", 1)[-1]
    (config.folder / name).touch()
    if name == "held":
        end = monotonic() + 20
        while not (config.folder / "release").exists() and monotonic() < end:
            sleep(0.01)
    return _WorkerId(os.getpid())


def _observe(path: Path) -> None:
    end = monotonic() + 8
    while not path.exists():
        assert monotonic() < end, "the first Page did not start"
        sleep(0.01)


async def test_a_page_cancelled_while_it_waits_is_never_prepared(tmp_path: Path) -> None:
    marks = tmp_path / "workers"
    marks.mkdir()
    hook = extractor("trace", _track, _Trace(marks))
    pool = PoolExecutor(1)
    await pool.start(PageSettings(scope=scope_rules(_URL), extractors=(hook,), strip_params=None))
    first = asyncio.create_task(pool.prepare(NormalizedUrl(_URL + "held"), _RESPONSE))
    try:
        await asyncio.to_thread(_observe, marks / "held")
        cancelled = asyncio.create_task(pool.prepare(NormalizedUrl(_URL + "cancelled"), _RESPONSE))
        last = asyncio.create_task(pool.prepare(NormalizedUrl(_URL + "last"), _RESPONSE))
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        (marks / "release").touch()
        before, after = await asyncio.wait_for(asyncio.gather(first, last), 8)
        output = hook.output(dict(before.outputs))
        assert output is not None
        assert output == hook.output(dict(after.outputs))
        assert {mark.name for mark in marks.iterdir()} == {"held", "release", "last"}
    finally:
        first.cancel()
        with suppress(asyncio.CancelledError):
            await first
        await asyncio.wait_for(pool.close(), 10)
