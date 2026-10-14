"""The pool executor: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import multiprocessing
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import psutil
import pytest
from selectolax.lexbor import LexborHTMLParser

from spider.cli.app import build_app
from spider.clock import SystemClock
from spider.crawl.fetcher import FetchResult
from spider.crawl.hooks import Handler, Hooks, UrlResult
from spider.crawl.pages import Extractor, PageInput, PageSettings, PreparedPage, prepare_page
from spider.crawl.parse_pool import PoolExecutor, default_workers, worker_count
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, plan_crawl, start_crawl
from spider.services.hooks import default_page_executor
from spider.store.records import SecretNames
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.app import settings_tables
from tests.support.crawling import crawl_result, crawled
from tests.support.workspace import TempWorkspace

URL = NormalizedUrl("https://site.test/")
BODY = b'<!doctype html><title>Home</title><a href="/about">About</a><img src="/logo.png">'
RESPONSE = FetchResult(
    status_code=200,
    headers=(("Content-Type", "text/html; charset=utf-8"),),
    body=BODY,
    fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
    response_time_ms=0,
)


class Prepared(msgspec.Struct, frozen=True):
    pid: int


def _record_pid(tree: LexborHTMLParser, page: PageInput) -> Prepared:
    # Long enough that concurrent Pages wait for a busy worker rather than reuse one at once.
    time.sleep(0.2)
    return Prepared(os.getpid())


class Unreadable(msgspec.Struct, frozen=True):
    """An output the crawl process cannot rebuild: its constructor runs again on unpickling."""

    url: str

    def __post_init__(self) -> None:
        if multiprocessing.parent_process() is None:
            raise ValueError("an Unreadable is built only in a worker")


def _unreadable_on_bad(tree: LexborHTMLParser, page: PageInput) -> msgspec.Struct:
    return Unreadable(page.url) if page.url.endswith("/bad") else Prepared(os.getpid())


# Module-level, so that a spawn worker imports them by name.
RECORD_PID = Extractor("record_pid", _record_pid)
SETTINGS = PageSettings(scope_rules(URL), (RECORD_PID,))
UNREADABLE_ON_BAD = Extractor("record_pid", _unreadable_on_bad)


def pid_of(outputs: tuple[tuple[str, msgspec.Struct], ...]) -> int:
    ((name, output),) = outputs
    assert name == RECORD_PID.name
    assert isinstance(output, Prepared)
    return output.pid


async def test_a_page_is_prepared_in_a_worker_process() -> None:
    pool = PoolExecutor(workers=2)
    await pool.start(SETTINGS)
    try:
        page = await pool.prepare(URL, RESPONSE)
        workers = pool.worker_pids
    finally:
        await pool.close()
    in_process = prepare_page(URL, RESPONSE, PageSettings(SETTINGS.scope))

    assert (page.links, page.parse_error, pid_of(page.outputs) in workers, os.getpid()) == (
        in_process.links,
        None,
        True,
        os.getpid(),
    )
    assert os.getpid() not in workers


async def test_pages_in_flight_are_spread_over_the_workers() -> None:
    pool = PoolExecutor(workers=2)
    await pool.start(SETTINGS)
    try:
        pages = await asyncio.gather(*(pool.prepare(URL, RESPONSE) for _ in range(6)))
        workers = pool.worker_pids
    finally:
        await pool.close()

    assert {pid_of(page.outputs) for page in pages} == set(workers)
    assert len(workers) == 2


async def test_close_ends_every_worker() -> None:
    pool = PoolExecutor(workers=2)
    await pool.start(SETTINGS)
    workers = pool.worker_pids

    await pool.close()

    assert [psutil.pid_exists(pid) for pid in workers] == [False, False]


def test_the_backlog_is_two_pages_per_worker() -> None:
    assert PoolExecutor(workers=3).backlog == 6


async def test_an_outcome_the_crawl_process_cannot_read_fails_only_its_page() -> None:
    pool = PoolExecutor(workers=1)
    await pool.start(PageSettings(scope_rules(URL), (UNREADABLE_ON_BAD,)))
    try:
        bad, good = await asyncio.gather(
            pool.prepare(NormalizedUrl("https://site.test/bad"), RESPONSE),
            pool.prepare(URL, RESPONSE),
            return_exceptions=True,
        )
        after = await pool.prepare(URL, RESPONSE)
    finally:
        await pool.close()

    assert (type(bad), str(bad)) == (ValueError, "an Unreadable is built only in a worker")
    assert isinstance(good, PreparedPage)
    assert [pid_of(page.outputs) for page in (good, after)] == list(pool.worker_pids) * 2


@pytest.mark.parametrize(
    ("physical", "logical", "available", "workers"),
    [
        # The maintainer's laptop: 8 physical cores of 12 logical ones gives 6 workers.
        (8, 12, 12, 6),
        # Without a physical count, half the logical ones.
        (None, 12, 12, 4),
        # A container's CPU limit caps the cores.
        (8, 12, 3, 1),
        (2, 4, 4, 1),
        (None, None, None, 1),
    ],
)
def test_the_workers_are_the_cores_less_two(
    physical: int | None, logical: int | None, available: int | None, workers: int
) -> None:
    assert worker_count(physical=physical, logical=logical, available=available) == workers


def test_the_default_worker_count_is_this_machines() -> None:
    available = getattr(os, "process_cpu_count", os.cpu_count)()

    assert default_workers() == worker_count(
        physical=psutil.cpu_count(logical=False), logical=os.cpu_count(), available=available
    )
    assert PoolExecutor().backlog == 2 * default_workers()


def test_the_default_page_executor_is_the_pool() -> None:
    assert isinstance(default_page_executor(), PoolExecutor)


def test_pages_are_parsed_outside_the_crawl_process(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a><a href="/b">B</a>'),
                "/a": Page(body="a"),
                "/b": Page(body="b"),
            }
        )
    )
    preparers: list[int] = []

    def record_preparer(result: UrlResult) -> tuple[()]:
        output = result.outputs.get(RECORD_PID.name)
        if isinstance(output, Prepared):
            preparers.append(output.pid)
        return ()

    hooks = Hooks(extractors=(RECORD_PID,), handlers=(Handler("preparers", record_preparer),))

    crawl_result(server.url("/"), hooks, pages=lambda: PoolExecutor(workers=2))

    assert (len(preparers), os.getpid() in preparers) == (3, False)


SMALL_SITE = Site(
    routes={
        "/": Page(body='<a href="/a">A</a><a href="/b">B</a>'),
        "/a": Page(body="a"),
        "/b": Page(body="b"),
    }
)


def preparers_of_a_service_crawl(seed: str) -> list[int]:
    """The processes that prepared each Page of a Crawl given no page executor, as the CLI's."""
    preparers: list[int] = []

    def record_preparer(result: UrlResult) -> tuple[()]:
        output = result.outputs.get(RECORD_PID.name)
        if isinstance(output, Prepared):
            preparers.append(output.pid)
        return ()

    request = CrawlRequest(
        seed=seed,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=None,
        command_argv=["spider", "crawl", seed],
        secret_names=SecretNames(),
        flags={},
    )
    hooks = Hooks(extractors=(RECORD_PID,), handlers=(Handler("preparers", record_preparer),))
    start_crawl(
        plan_crawl(request, settings_tables(build_app())), SystemClock(), Collected(), hooks
    )
    return preparers


def test_a_crawl_in_the_suite_prepares_its_pages_in_process(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    preparers = preparers_of_a_service_crawl(fixture_site(SMALL_SITE).url("/"))

    assert preparers == [os.getpid()] * 3


@pytest.mark.parse_pool
def test_a_crawl_marked_parse_pool_prepares_its_pages_in_the_pool(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    preparers = preparers_of_a_service_crawl(fixture_site(SMALL_SITE).url("/"))

    assert (len(preparers), os.getpid() in preparers) == (3, False)


@pytest.mark.parse_pool
def test_spider_crawl_starts_its_parse_workers(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SMALL_SITE)
    children: set[int] = set()
    done = threading.Event()

    def watch() -> None:
        this = psutil.Process()
        while not done.wait(0.02):
            children.update(child.pid for child in this.children())

    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        crawled(server.url("/"))
    finally:
        done.set()
        watcher.join()

    assert len(children) >= 1
