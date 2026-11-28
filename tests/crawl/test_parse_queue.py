"""Bound and cancel queued preparation through the Crawl Service and worker pool."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from time import monotonic, sleep

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.engine.hooks import UrlResult, handler
from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.parse_pool import PoolExecutor
from openlinx.crawl.pages.preparation import PageInput, PageSettings, extractor
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.services.hooks import default_hooks
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace

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
    hold_children: bool = False


class _WorkerId(msgspec.Struct, frozen=True):
    pid: int


def _track(tree: LexborHTMLParser, page: PageInput, config: _Trace) -> _WorkerId:
    name = page.url.rsplit("/", 1)[-1]
    if name:
        (config.folder / name).touch()
    if config.hold_children and name:
        (config.folder / "started").touch()
    if name == "held" or (config.hold_children and name):
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


def test_fetching_waits_for_slow_parsing(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    paths = tuple(f"/p{index}" for index in range(1, 10))
    site = fixture_site(
        Site(
            routes={
                "/": Page(body="".join(f'<a href="{path}">{path}</a>' for path in paths)),
                **{path: Page(body="<p>Page</p>") for path in paths},
            }
        )
    )
    marks = tmp_path / "workers"
    marks.mkdir()
    prepared: dict[str, float] = {}

    def observe_preparation(result: UrlResult) -> tuple[None, ...]:
        if result.parsed:
            prepared[result.url] = monotonic()
        return ()

    hooks = default_hooks()
    hooks = replace(
        hooks,
        extractors=(
            *hooks.extractors,
            extractor("trace", _track, _Trace(marks, hold_children=True)),
        ),
        handlers=(
            *hooks.handlers,
            handler("prepared", observe_preparation, lambda _db, _rows: None),
        ),
    )

    def received() -> list[str]:
        return [
            request.path
            for request in site.requests
            if request.method == "GET" and request.path in paths
        ]

    def release_after_pressure() -> None:
        try:
            _observe(marks / "started")
            end = monotonic() + 8
            while len(received()) < 7:
                assert monotonic() < end, "the host's window did not fill"
                sleep(0.01)
            # Ensure the host remains saturated with more requests ready to start.
            end = monotonic() + 1
            while len(received()) < len(paths) and monotonic() < end:
                sleep(0.01)
        finally:
            (marks / "release").touch()

    with ThreadPoolExecutor(max_workers=1) as observer:
        release = observer.submit(release_after_pressure)
        result = crawl_result(site.url("/"), hooks, pages=partial(PoolExecutor, workers=1))
        release.result()

    expected = [site.url(path) for path in ("/", *paths)]
    assert result.failure is None
    assert crawl_row(result.crawl_file)["state"] == "completed"
    assert query(result.crawl_file, "SELECT url, parsed, parse_error FROM urls ORDER BY url") == [
        (url, 1, None) for url in expected
    ]

    assert sorted(prepared) == expected
    # The handler sees each prepared Page after the worker replies. Count the actual GETs
    # up to every request timestamp, excluding Pages already handed back to the Crawl.
    arrivals = [
        request for request in site.requests if request.method == "GET" and request.path in paths
    ]
    assert sorted(request.path for request in arrivals) == list(paths)
    peak = max(
        sum(request.received_at <= at < prepared[site.url(request.path)] for request in arrivals)
        for at in (request.received_at for request in arrivals)
    )
    assert peak == 7, [(request.path, request.received_at) for request in arrivals]
