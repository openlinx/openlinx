"""Exercise worker preparation through the Crawl Service and the read-only crawl file."""

import os
import threading
from collections.abc import Sequence
from dataclasses import replace
from functools import partial
from multiprocessing.process import BaseProcess
from pathlib import Path

import msgspec
import psutil
import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection, text

from openlinx.crawl.engine.hooks import UrlResult, handler
from openlinx.crawl.pages.parse_pool import PoolExecutor
from openlinx.crawl.pages.preparation import PageInput, extractor
from openlinx.services.hooks import default_hooks
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


class _Config(msgspec.Struct, frozen=True):
    marker: str


class _PreparedIn(msgspec.Struct, frozen=True):
    pid: int
    marker: str


def _observe(tree: LexborHTMLParser, page: PageInput, config: _Config) -> _PreparedIn:
    return _PreparedIn(os.getpid(), config.marker)


_OBSERVER = extractor("preparation_process", _observe, _Config("from snapshot"))


def _observations(result: UrlResult) -> tuple[tuple[str, int, int, str], ...]:
    output = _OBSERVER.output(result.outputs)
    if output is None:
        return ()
    return ((result.url, output.pid, os.getpid(), output.marker),)


def _write(connection: Connection, rows: Sequence[tuple[str, int, int, str]]) -> None:
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS test_preparation (url TEXT, worker INTEGER,"
        " handler INTEGER, marker TEXT)"
    )
    connection.execute(
        text("INSERT INTO test_preparation VALUES (:url, :worker, :handler, :marker)"),
        [
            {"url": url, "worker": worker, "handler": process, "marker": marker}
            for url, worker, process, marker in rows
        ],
    )


def test_pages_are_parsed_outside_the_crawl_process(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    site = fixture_site(
        Site(routes={"/": Page(body='<a href="/about">About</a>'), "/about": Page(body="About")})
    )
    hooks = default_hooks()
    hooks = replace(
        hooks,
        extractors=(*hooks.extractors, _OBSERVER),
        handlers=(*hooks.handlers, handler("preparation_process", _observations, _write)),
    )

    result = crawl_result(site.url("/"), hooks, pages=partial(PoolExecutor, workers=1))

    assert result.failure is None
    assert crawl_row(result.crawl_file)["state"] == "completed"
    assert query(result.crawl_file, "SELECT url, parsed, parse_error FROM urls ORDER BY url") == [
        (site.url("/"), 1, None),
        (site.url("/about"), 1, None),
    ]
    rows = query(
        result.crawl_file, "SELECT url, worker, handler, marker FROM test_preparation ORDER BY url"
    )
    assert [(url, process, marker) for url, _, process, marker in rows] == [
        (site.url("/"), os.getpid(), "from snapshot"),
        (site.url("/about"), os.getpid(), "from snapshot"),
    ]
    workers = {worker for _, worker, _, _ in rows}
    assert len(workers) == 1
    assert os.getpid() not in workers
    assert all(not psutil.pid_exists(pid) for pid in workers)


class _Failure(msgspec.Struct, frozen=True):
    folder: Path
    crash: bool


def _fail_on_bad_page(tree: LexborHTMLParser, page: PageInput, config: _Failure) -> _PreparedIn:
    if page.url.endswith("/bad"):
        (config.folder / str(os.getpid())).touch()
        if config.crash:
            os._exit(3)
        threading.Event().wait(90)
    return _PreparedIn(os.getpid(), "from replacement")


@pytest.mark.parametrize(
    ("crash", "parse_error"),
    [(True, "worker_crashed"), (False, "parse_timeout")],
    ids=["native-exit", "deadline"],
)
def test_worker_failure_records_only_its_page_and_starts_a_replacement(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    crash: bool,
    parse_error: str,
) -> None:
    site = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/bad">Bad</a>'),
                "/bad": Page(
                    body='<a href="/lost">Link lost with the worker</a>',
                    headers=(("Link", "</ok>; rel=canonical"),),
                ),
                "/ok": Page(body="Next Page"),
            }
        )
    )
    marks = tmp_path / "workers"
    marks.mkdir()
    failure = extractor("preparation_process", _fail_on_bad_page, _Failure(marks, crash))
    hooks = default_hooks()
    hooks = replace(
        hooks,
        extractors=(*hooks.extractors, failure),
        handlers=(*hooks.handlers, handler("preparation_process", _observations, _write)),
    )

    spawned: list[int] = []
    start = BaseProcess.start

    def observe_start(process: BaseProcess) -> None:
        if process.name == "parse-worker-1":
            (first,) = spawned
            assert not psutil.pid_exists(first), f"Original worker PID {first} is still unreaped"
        start(process)
        if process.name in {"parse-worker-0", "parse-worker-1"}:
            assert process.pid is not None
            spawned.append(process.pid)

    monkeypatch.setattr(BaseProcess, "start", observe_start)
    result = crawl_result(site.url("/"), hooks, pages=partial(PoolExecutor, workers=1, deadline=2))

    assert result.failure is None
    assert crawl_row(result.crawl_file)["state"] == "completed"
    assert query(result.crawl_file, "SELECT url, parsed, parse_error FROM urls ORDER BY url") == [
        (site.url("/"), 1, None),
        (site.url("/bad"), 0, parse_error),
        (site.url("/ok"), 1, None),
    ]
    rows = query(result.crawl_file, "SELECT url, worker FROM test_preparation ORDER BY url")
    assert [url for url, _ in rows] == [site.url("/"), site.url("/ok")]
    first, replacement = (pid for _, pid in rows)
    assert [mark.name for mark in marks.iterdir()] == [str(first)]
    assert first != replacement
    assert spawned == [first, replacement]
    assert all(not psutil.pid_exists(pid) for pid in (first, replacement))
