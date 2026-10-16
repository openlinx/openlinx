"""The parse pool: page preparation in worker processes (design D1 of 026-add-parse-pool)."""

import asyncio
import multiprocessing
import os
import pickle
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import msgspec
import psutil
import pytest
from selectolax.lexbor import LexborHTMLParser

from spider.cli.app import build_app
from spider.clock import SystemClock
from spider.crawl import parse_pool
from spider.crawl.fetcher import FetchResult
from spider.crawl.hooks import Handler, Hooks, UrlResult
from spider.crawl.pages import Extractor, PageInput, PageSettings, PreparedPage, prepare_page
from spider.crawl.parse_pool import (
    PREPARE_DEADLINE_SECONDS,
    PoolExecutor,
    WorkerStartError,
    _outcome,
    _pickled,
    _work,
    cpu_quota,
    default_workers,
    worker_count,
    worker_limit,
)
from spider.crawl.politeness import global_cap
from spider.crawl.scope import scope_rules
from spider.crawl.settings import CrawlSettings
from spider.crawl.urls import NormalizedUrl
from spider.output.reporter import Collected
from spider.services.crawling import CrawlRequest, CrawlResult, plan_crawl, start_crawl
from spider.services.hooks import default_page_executor
from spider.store.records import SecretNames
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site
from tests.support.app import settings_tables
from tests.support.cli import run_cli, run_cli_process
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

SITE = "https://site.test"
RESPONSE = FetchResult(
    status_code=200,
    headers=(("Content-Type", "text/html; charset=utf-8"),),
    body=b'<!doctype html><title>Home</title><a href="/about">About</a><img src="/logo.png">',
    fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
    response_time_ms=0,
)
SMALL_SITE = Site(
    routes={
        "/": Page(body='<a href="/a">A</a><a href="/b">B</a>'),
        "/a": Page(body="a"),
        "/b": Page(body="b"),
    }
)
# A worker that is told to wait stays long enough busy for a test to act meanwhile.
BUSY_SECONDS = 0.3
# Longer than any test waits for a Page: such a Page ends only with its worker.
HANG_SECONDS = 120
# A deadline short enough for a test, and a Page that ends after it (design D8).
LATE_DEADLINE = 1.0
LATE_SECONDS = LATE_DEADLINE + 0.5


def at(path: str) -> NormalizedUrl:
    return NormalizedUrl(SITE + path)


class Preparer(msgspec.Struct, frozen=True):
    pid: int
    # The Pages this worker had prepared, this one included.
    count: int


# Per process: each worker counts its own Pages.
_prepared_here = 0
# A folder where the workers holding a /meet Page leave their pid, named in the environment that
# a spawn worker inherits; each waits there until MEETING_WORKERS of them hold one at once.
MEETING_FOLDER = "SPIDER_TEST_MEETING_FOLDER"
MEETING_WORKERS = 2


def _meet(folder: Path) -> None:
    (folder / str(os.getpid())).touch()
    # Bounded, so a pool that never gives a second worker a Page fails the test, not hangs it.
    give_up = time.monotonic() + 20
    while len(list(folder.iterdir())) < MEETING_WORKERS and time.monotonic() < give_up:
        time.sleep(0.01)


def _record_preparer(tree: LexborHTMLParser, page: PageInput) -> Preparer:
    global _prepared_here
    _prepared_here += 1
    if page.url.endswith("/die"):
        # As a crashing native parser would: no exception, no cleanup.
        os._exit(3)
    if page.url.endswith("/meet"):
        _meet(Path(os.environ[MEETING_FOLDER]))
    if page.url.endswith("/busy"):
        time.sleep(BUSY_SECONDS)
    if page.url.endswith("/hang"):
        time.sleep(HANG_SECONDS)
    if page.url.endswith("/late"):
        time.sleep(LATE_SECONDS)
    return Preparer(os.getpid(), _prepared_here)


class Unreadable(msgspec.Struct, frozen=True):
    """An output the crawl process cannot rebuild: its constructor runs again on unpickling."""

    url: str

    def __post_init__(self) -> None:
        if multiprocessing.parent_process() is None:
            raise ValueError("an Unreadable is built only in a worker")


def _unreadable_on_bad(tree: LexborHTMLParser, page: PageInput) -> msgspec.Struct:
    return Unreadable(page.url) if page.url.endswith("/bad") else Preparer(os.getpid(), 0)


class Holder(msgspec.Struct, frozen=True):
    value: Any


def _unpicklable_on_odd(tree: LexborHTMLParser, page: PageInput) -> Holder:
    return Holder((lambda: None) if page.url.endswith("/odd") else None)


# Module-level, so that a spawn worker imports them by name.
RECORD_PREPARER = Extractor("record_preparer", _record_preparer)
UNREADABLE_ON_BAD = Extractor("unreadable_on_bad", _unreadable_on_bad)
UNPICKLABLE_ON_ODD = Extractor("unpicklable_on_odd", _unpicklable_on_odd)

# The scenario's slow parsing, against fetches of a few milliseconds from the fixture site.
SLOW_SECONDS = 1.0


class Slept(msgspec.Struct, frozen=True):
    pass


def _slow_everywhere(tree: LexborHTMLParser, page: PageInput) -> Slept:
    time.sleep(SLOW_SECONDS)
    return Slept()


SLOW_EVERYWHERE = Extractor("slow_everywhere", _slow_everywhere)

# The scenarios' deadline, shortened as the spec allows; every other Page takes a third of it.
TEST_DEADLINE = 1.5


def _never_ends_on_slow(tree: LexborHTMLParser, page: PageInput) -> Slept:
    time.sleep(HANG_SECONDS if page.url.endswith("/slow") else TEST_DEADLINE / 3)
    return Slept()


NEVER_ENDS_ON_SLOW = Extractor("never_ends_on_slow", _never_ends_on_slow)


def preparer(page: PreparedPage | BaseException) -> Preparer:
    assert isinstance(page, PreparedPage)
    output = dict(page.outputs)[RECORD_PREPARER.name]
    assert isinstance(output, Preparer)
    return output


@asynccontextmanager
async def started(
    workers: int,
    *extractors: Extractor,
    deadline: float = PREPARE_DEADLINE_SECONDS,
    ready_deadline: float = PREPARE_DEADLINE_SECONDS,
) -> AsyncIterator[PoolExecutor]:
    pool = PoolExecutor(workers=workers, deadline=deadline, ready_deadline=ready_deadline)
    await pool.start(PageSettings(scope_rules(at("/")), extractors or (RECORD_PREPARER,)))
    try:
        yield pool
    finally:
        await pool.close()


@pytest.mark.slow
async def test_a_page_is_prepared_in_a_worker_as_in_process() -> None:
    async with started(2) as pool:
        page = await pool.prepare(at("/"), RESPONSE)
        workers = pool.worker_pids
    in_process = prepare_page(at("/"), RESPONSE, PageSettings(scope_rules(at("/"))))

    assert (page.document_links, preparer(page).pid in workers) == (
        in_process.document_links,
        True,
    )


@pytest.mark.slow
async def test_pages_in_flight_are_spread_over_the_workers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A worker takes Pages once it is ready, so the first one ready could otherwise take them
    # all: each holds its /meet Page until the other holds one too.
    meeting = tmp_path / "meeting"
    meeting.mkdir()
    monkeypatch.setenv(MEETING_FOLDER, str(meeting))
    async with started(MEETING_WORKERS) as pool:
        meetings = (pool.prepare(at("/meet"), RESPONSE) for _ in range(MEETING_WORKERS))
        pages = await asyncio.gather(*meetings)
        workers = pool.worker_pids

    assert sorted({preparer(page).pid for page in pages}) == sorted(workers)


@pytest.mark.slow
async def test_close_ends_every_worker() -> None:
    async with started(2) as pool:
        workers = pool.worker_pids

    assert [psutil.pid_exists(pid) for pid in workers] == [False, False]


def test_the_backlog_is_two_pages_per_worker() -> None:
    assert PoolExecutor(workers=3).backlog == 6


@pytest.mark.parametrize("workers", [0, 3])
def test_a_worker_count_the_pool_cannot_run_is_refused(
    monkeypatch: pytest.MonkeyPatch, workers: int
) -> None:
    # As on Windows before Python 3.13, with a lower limit.
    monkeypatch.setattr(parse_pool, "_waiter_limit", lambda: 2)

    with pytest.raises(ValueError, match="parse workers"):
        PoolExecutor(workers=workers)


async def test_a_page_given_before_the_pool_starts_is_refused() -> None:
    with pytest.raises(RuntimeError, match="before it is started"):
        await PoolExecutor(workers=1).prepare(at("/"), RESPONSE)


async def test_a_pool_that_never_started_closes_cleanly() -> None:
    # 020's Crawl closes its executor in a finally, also when the writer failed before start().
    await asyncio.wait_for(PoolExecutor(workers=1).close(), timeout=30)


@pytest.mark.slow
async def test_an_output_the_crawl_process_cannot_read_costs_only_its_extractor() -> None:
    async with started(1, RECORD_PREPARER, UNREADABLE_ON_BAD) as pool:
        page = await pool.prepare(at("/bad"), RESPONSE)

    assert (
        [name for name, _ in page.outputs],
        len(page.document_links),
        page.parse_error,
        page.parse_error_message,
    ) == ([RECORD_PREPARER.name], 2, "extractor_error", "unreadable_on_bad: ValueError")


@pytest.mark.slow
async def test_an_output_a_worker_cannot_send_costs_only_its_extractor() -> None:
    async with started(1, RECORD_PREPARER, UNPICKLABLE_ON_ODD) as pool:
        page = await pool.prepare(at("/odd"), RESPONSE)

    assert ([name for name, _ in page.outputs], page.parse_error, page.parse_error_message) == (
        [RECORD_PREPARER.name],
        "extractor_error",
        "unpicklable_on_odd: PicklingError",
    )


def test_an_outcome_that_cannot_cross_even_without_its_outputs_fails_its_page() -> None:
    page = prepare_page(at("/"), RESPONSE, PageSettings(scope_rules(at("/"))))
    unsendable = msgspec.structs.replace(page, document_links=(lambda: None,))

    assert type(pickle.loads(_pickled(unsendable))) is RuntimeError  # noqa: S301


@pytest.mark.slow
def test_a_worker_whose_crawl_process_has_ended_ends_quietly() -> None:
    spawn = multiprocessing.get_context("spawn")
    task_reader, task_writer = spawn.Pipe(duplex=False)
    result_reader, result_writer = spawn.Pipe(duplex=False)
    worker = spawn.Process(target=_work, args=(task_reader, result_writer))
    worker.start()
    task_reader.close()
    result_writer.close()
    task_writer.send(PageSettings(scope_rules(at("/"))))
    # Its ready answer: the outcome's send is the one that must fail.
    result_reader.recv_bytes()
    # As a second Ctrl+C ends the crawl process while its worker prepares a Page.
    result_reader.close()
    task_writer.send((at("/"), RESPONSE))
    worker.join(timeout=30)
    task_writer.close()

    assert worker.exitcode == 0


@pytest.mark.slow
async def test_a_worker_that_ends_costs_only_the_page_it_held() -> None:
    async with started(2) as pool:
        ended, other = await asyncio.wait_for(
            asyncio.gather(pool.prepare(at("/die"), RESPONSE), pool.prepare(at("/"), RESPONSE)),
            timeout=30,
        )

    assert (ended.parse_error, ended.document_links, other.parse_error) == (
        "worker_crashed",
        (),
        None,
    )


@pytest.mark.slow
async def test_a_worker_that_ends_is_replaced() -> None:
    async with started(1) as pool:
        first = preparer(await pool.prepare(at("/"), RESPONSE)).pid
        # The Page after it waits for the replacement.
        _, after = await asyncio.wait_for(
            asyncio.gather(pool.prepare(at("/die"), RESPONSE), pool.prepare(at("/"), RESPONSE)),
            timeout=30,
        )

    assert preparer(after).pid not in (first, os.getpid())


class RaisesOnLoad:
    """A record that pickles in a worker and cannot be rebuilt in the crawl process."""

    def __reduce__(self) -> tuple[Callable[[], None], tuple[()]]:
        return (_refuse, ())


def _refuse() -> None:
    raise ValueError("this record cannot be rebuilt here")


def test_a_page_whose_record_cannot_be_read_is_recorded_as_crashed() -> None:
    page = _outcome(pickle.dumps(RaisesOnLoad()))

    assert isinstance(page, PreparedPage)
    assert (page.parse_error, page.parse_error_message) == (
        "worker_crashed",
        "The Page's record from its parse worker could not be read: ValueError: this record "
        "cannot be rebuilt here",
    )


@pytest.mark.slow
async def test_a_worker_that_cannot_start_fails_the_crawl() -> None:
    # Imported here: the workers of the other tests import this module.
    from tests.crawl.unimportable_in_workers import UNIMPORTABLE_IN_WORKERS

    async with started(1, UNIMPORTABLE_IN_WORKERS) as pool:
        outcome = await asyncio.wait_for(
            asyncio.gather(pool.prepare(at("/"), RESPONSE), return_exceptions=True), 30
        )

    assert [type(error) for error in outcome] == [WorkerStartError]


@pytest.mark.slow
async def test_a_worker_ended_from_outside_costs_its_page_at_once() -> None:
    async with started(1) as pool:
        # Answered, so the worker has started and is idle.
        await pool.prepare(at("/"), RESPONSE)
        held = asyncio.ensure_future(pool.prepare(at("/hang"), RESPONSE))
        # The Page has reached the worker's pipe.
        await asyncio.sleep(0)
        psutil.Process(pool.worker_pids[0]).terminate()
        # Seen through its result pipe's end, long before any deadline (design D1).
        outcome = await asyncio.wait_for(asyncio.gather(held), 10)

    assert [page.parse_error for page in outcome] == ["worker_crashed"]


@pytest.mark.slow
async def test_an_outcome_that_comes_after_its_deadline_is_dropped() -> None:
    loop = asyncio.get_running_loop()
    # A loop callback that raises only reaches the handler, never the test.
    errors: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, context: errors.append(context))
    async with started(1, deadline=LATE_DEADLINE) as pool:
        # Answered, so the worker is ready and idle.
        await pool.prepare(at("/"), RESPONSE)
        late = asyncio.ensure_future(pool.prepare(at("/late"), RESPONSE))
        await asyncio.sleep(0)
        due = loop.time() + LATE_DEADLINE
        # The first hold spans the deadline, so its timer and the second hold, due just before
        # it, run in one pass of the loop, the hold first; the worker sends its outcome during
        # the second hold, so the outcome reaches the loop after the deadline's timer has run.
        loop.call_at(due - 0.1, time.sleep, 0.2)
        loop.call_at(due - 0.05, time.sleep, LATE_SECONDS)
        page = await asyncio.wait_for(late, 30)
        # The replacement prepares the next Page.
        await asyncio.wait_for(pool.prepare(at("/"), RESPONSE), 30)
        started_workers = len(pool.worker_pids)

    assert (page.parse_error, started_workers, errors) == ("parse_timeout", 2, [])


@pytest.mark.slow
async def test_a_worker_that_is_never_ready_fails_the_crawl() -> None:
    # Imported here: the workers of the other tests import this module.
    from tests.crawl.hangs_in_workers import HANGS_IN_WORKERS

    async with started(1, HANGS_IN_WORKERS, ready_deadline=LATE_DEADLINE) as pool:
        outcome = await asyncio.wait_for(
            asyncio.gather(pool.prepare(at("/"), RESPONSE), return_exceptions=True), 30
        )
        started_workers = len(pool.worker_pids)

    assert ([type(error) for error in outcome], started_workers) == ([WorkerStartError], 1)


@pytest.mark.slow
async def test_a_page_cancelled_while_it_waits_is_never_prepared() -> None:
    async with started(1) as pool:
        busy = asyncio.ensure_future(pool.prepare(at("/busy"), RESPONSE))
        cancelled = asyncio.ensure_future(pool.prepare(at("/cancelled"), RESPONSE))
        last = asyncio.ensure_future(pool.prepare(at("/last"), RESPONSE))
        # Each has reached the pool: the first holds the one worker, the others wait.
        await asyncio.sleep(0)
        cancelled.cancel()
        pages = await asyncio.gather(busy, last)

    assert [preparer(page).count for page in pages] == [1, 2]


@pytest.mark.slow
async def test_the_pool_closes_after_a_worker_has_ended() -> None:
    async with started(2) as pool:
        ended = psutil.Process(pool.worker_pids[0])
        ended.kill()
        ended.wait(timeout=30)

    assert [thread.name for thread in threading.enumerate() if "spider-parse" in thread.name] == []


@pytest.mark.parametrize(
    ("physical", "logical", "available", "quota", "limit", "workers"),
    [
        # The maintainer's laptop: 8 physical cores of 12 logical ones gives 6 workers.
        (8, 12, 12, None, None, 6),
        # Without a physical count, half the logical ones.
        (None, 12, 12, None, None, 4),
        # Only part of the machine is ours (taskset, a container's cpuset): as many physical
        # cores as its share of the logical ones.
        (8, 16, 8, None, None, 2),
        (8, 12, 3, None, None, 1),
        (2, 4, 4, None, None, 1),
        (None, None, None, None, None, 1),
        # A CPU quota (docker --cpus=2, a Kubernetes limit) on a 16-core host.
        (16, 32, 32, 2, None, 1),
        (16, 32, 32, 9, None, 7),
        (8, 12, 12, 100, None, 6),
        # No more than the waiter thread can watch.
        (128, 256, 256, None, 62, 62),
    ],
)
def test_the_workers_are_the_available_physical_cores_less_two(
    physical: int | None,
    logical: int | None,
    available: int | None,
    quota: int | None,
    limit: int | None,
    workers: int,
) -> None:
    count = worker_count(
        physical=physical, logical=logical, available=available, quota=quota, limit=limit
    )

    assert count == workers


@pytest.mark.parametrize(
    ("platform", "version", "limit"),
    [
        # connection.wait takes at most 63 handles there: one per worker and the wake pipe.
        ("win32", (3, 12), 62),
        ("win32", (3, 13), None),
        ("linux", (3, 12), None),
        ("darwin", (3, 12), None),
    ],
)
def test_the_workers_are_no_more_than_the_waiter_can_watch(
    platform: str, version: tuple[int, int], limit: int | None
) -> None:
    assert worker_limit(platform, version) == limit


@pytest.mark.parametrize(
    ("membership", "files", "quota"),
    [
        # A container in its own cgroup namespace: docker --cpus=2.
        ("0::/\n", {"cpu.max": "200000 100000\n"}, 2),
        ("0::/\n", {"cpu.max": "max 100000\n"}, None),
        # Part of a CPU counts as a whole one.
        ("0::/\n", {"cpu.max": "150000 100000\n"}, 2),
        # A Kubernetes pod's limit sits on an ancestor: the lowest on the way to the root counts.
        (
            "0::/kubepods/pod/c\n",
            {"kubepods/pod/cpu.max": "400000 100000\n", "kubepods/pod/c/cpu.max": "max 100000\n"},
            4,
        ),
        ("0::/a\n", {"cpu.max": "800000 100000\n", "a/cpu.max": "300000 100000\n"}, 3),
        # cgroup v1 only, or no /proc (macOS, Windows): no quota is seen.
        ("1:cpu,cpuacct:/\n", {}, None),
        (None, {}, None),
    ],
)
def test_a_cgroup_cpu_quota_is_read(
    tmp_path: Path, membership: str | None, files: dict[str, str], quota: int | None
) -> None:
    root = tmp_path / "cgroup"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, newline="\n")
    if membership is not None:
        (tmp_path / "self").write_text(membership, newline="\n")

    assert cpu_quota(root, tmp_path / "self") == quota


def test_the_default_worker_count_reads_this_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 16 physical cores of 32 logical ones, 24 of them available, under a quota of 9 CPUs.
    monkeypatch.setattr(psutil, "cpu_count", lambda logical=True: 32 if logical else 16)
    monkeypatch.setattr(os, "cpu_count", lambda: 32)
    monkeypatch.setattr(os, "process_cpu_count", lambda: 24, raising=False)
    (tmp_path / "crawl").mkdir()
    (tmp_path / "crawl" / "cpu.max").write_text("900000 100000\n", newline="\n")
    (tmp_path / "self").write_text("0::/crawl\n", newline="\n")
    monkeypatch.setattr(parse_pool, "_CGROUP_ROOT", tmp_path)
    monkeypatch.setattr(parse_pool, "_SELF_CGROUP", tmp_path / "self")

    assert default_workers() == 7


def test_the_default_page_executor_is_the_pool() -> None:
    assert isinstance(default_page_executor(), PoolExecutor)


def recording_preparers() -> tuple[Hooks, list[int]]:
    """Hooks with the test extractor and a handler that lists the process of each Page's."""
    preparers: list[int] = []

    def record(result: UrlResult) -> tuple[()]:
        output = result.outputs.get(RECORD_PREPARER.name)
        if isinstance(output, Preparer):
            preparers.append(output.pid)
        return ()

    return Hooks(extractors=(RECORD_PREPARER,), handlers=(Handler("preparers", record),)), preparers


def crawl_without_a_page_executor(seed: str, hooks: Hooks) -> None:
    """Through the Crawl Service, given no page executor, as the CLI calls it."""
    request = CrawlRequest(
        seed=seed,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=None,
        command_argv=["spider", "crawl", seed],
        secret_names=SecretNames(),
        flags={},
    )
    plan = plan_crawl(request, settings_tables(build_app()))
    start_crawl(plan, SystemClock(), Collected(), hooks)


@pytest.mark.slow
def test_pages_are_parsed_outside_the_crawl_process(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    hooks, preparers = recording_preparers()

    crawl_result(fixture_site(SMALL_SITE).url("/"), hooks, pages=lambda: PoolExecutor(workers=2))

    assert (len(preparers), os.getpid() in preparers) == (3, False)


def test_a_crawl_in_the_suite_prepares_its_pages_in_process(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    hooks, preparers = recording_preparers()

    crawl_without_a_page_executor(fixture_site(SMALL_SITE).url("/"), hooks)

    assert preparers == [os.getpid()] * 3


@pytest.mark.slow
@pytest.mark.parse_pool
def test_a_crawl_marked_parse_pool_prepares_its_pages_in_the_pool(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    hooks, preparers = recording_preparers()

    crawl_without_a_page_executor(fixture_site(SMALL_SITE).url("/"), hooks)

    assert (len(preparers), os.getpid() in preparers) == (3, False)


@pytest.mark.slow
def test_fetching_waits_for_slow_parsing(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    paths = [f"/p{n}" for n in range(1, 51)]
    links = "".join(f'<a href="{path}">{path}</a>' for path in paths)
    routes: dict[str, Route] = {"/": Page(body=links)}
    routes |= {path: Page(body=path) for path in paths}
    server = fixture_site(Site(routes=routes))
    pages = {server.url(path) for path in ["/", *paths]}
    # Seen by a handler in the crawl process, after the Page's preparation has ended.
    prepared: list[float] = []

    def record(result: UrlResult) -> tuple[()]:
        if result.url in pages:
            prepared.append(time.monotonic())
        return ()

    hooks = Hooks(extractors=(SLOW_EVERYWHERE,), handlers=(Handler("prepared", record),))
    crawl_result(server.url("/"), hooks, pages=lambda: PoolExecutor(workers=2))

    requested = [r.received_at for r in server.requests if server.url(r.path) in pages]
    most = max(sum(t <= at for t in requested) - sum(t <= at for t in prepared) for at in requested)
    assert most <= global_cap(CrawlSettings.model_validate({}).concurrency) + 2 * 2


CRASH_SITE = Site(
    routes={
        "/": Page(body='<a href="/die">Die</a><a href="/ok">OK</a>'),
        "/die": Page(body="die"),
        "/ok": Page(body="ok"),
    }
)


@pytest.mark.slow
def test_a_crashed_worker_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(CRASH_SITE)
    hooks, _ = recording_preparers()

    crawl_file = crawl_result(
        server.url("/"), hooks, pages=lambda: PoolExecutor(workers=1)
    ).crawl_file

    assert query(
        crawl_file, "SELECT parsed, parse_error FROM urls WHERE url = ?", (server.url("/die"),)
    ) == [(0, "worker_crashed")]


@pytest.mark.slow
def test_the_crawl_continues_after_a_worker_crash(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(CRASH_SITE)
    hooks, _ = recording_preparers()

    # One worker: /ok is prepared by the replacement of the worker /die ended.
    result = crawl_result(server.url("/"), hooks, pages=lambda: PoolExecutor(workers=1))

    parsed = query(result.crawl_file, "SELECT parsed FROM urls WHERE url = ?", (server.url("/ok"),))
    assert (parsed, result.summary.state) == ([(1,)], "completed")


SLOW_SITE = Site(
    routes={
        "/": Page(body='<a href="/slow">Slow</a><a href="/ok">OK</a>'),
        "/slow": Page(body="slow"),
        "/ok": Page(body="ok"),
    }
)


def crawl_with_a_short_deadline(seed: str, workers: int = 1) -> CrawlResult:
    hooks = Hooks(extractors=(NEVER_ENDS_ON_SLOW,))
    return crawl_result(
        seed, hooks, pages=lambda: PoolExecutor(workers=workers, deadline=TEST_DEADLINE)
    )


@pytest.mark.slow
def test_a_page_that_takes_too_long_to_prepare_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_SITE)

    crawl_file = crawl_with_a_short_deadline(server.url("/")).crawl_file

    assert query(
        crawl_file, "SELECT parsed, parse_error FROM urls WHERE url = ?", (server.url("/slow"),)
    ) == [(0, "parse_timeout")]


@pytest.mark.slow
def test_the_crawl_continues_after_a_preparation_timeout(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_SITE)

    # One worker: /ok is prepared by the replacement of the worker that /slow held.
    result = crawl_with_a_short_deadline(server.url("/"))

    parsed = query(result.crawl_file, "SELECT parsed FROM urls WHERE url = ?", (server.url("/ok"),))
    assert (parsed, result.summary.state) == ([(1,)], "completed")


@pytest.mark.slow
@pytest.mark.parse_pool
def test_the_number_of_parse_workers_is_reported(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    result = run_cli("crawl", fixture_site(SMALL_SITE).url("/"))

    started_event = next(line for line in result.stderr_json_lines() if line.get("event"))
    assert (started_event["event"], started_event["data"]["parse_workers"]) == (
        "crawl_started",
        default_workers(),
    )


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="spawn's Windows path: a new interpreter")
def test_pages_are_parsed_in_worker_processes_on_windows(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/about">About</a>'), "/about": Page(body="about")})
    )

    # A real spider process, which the suite's in-process double does not reach.
    result = run_cli_process("crawl", server.url("/"))

    parsed = query(
        Path(result.json()["crawl_file"]),
        "SELECT parsed FROM urls WHERE url = ?",
        (server.url("/about"),),
    )
    assert (result.exit_code, parsed) == (0, [(1,)])
