"""The pool executor: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import multiprocessing
import os
import time
from datetime import UTC, datetime

import msgspec
import psutil
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import Extractor, PageInput, PageSettings, PreparedPage, prepare_page
from spider.crawl.parse_pool import PoolExecutor
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl

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
