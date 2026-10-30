"""The page executor's lifecycle, through the Crawl Service (020-add-crawl-core D9; seam 3)."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext
from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import PageSettings, PreparedPage, prepare_page
from openlinx.crawl.urls import NormalizedUrl
from openlinx.output.diagnostics import Diagnostic
from openlinx.output.reporter import Collected
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

TWO_PAGES = Site(routes={"/": Page(body='<a href="/a">A</a>'), "/a": Page(body="<p>A</p>")})


class RecordingExecutor:
    """Page preparation in process, recording when it is started, used and closed."""

    def __init__(self, workers: int = 0) -> None:
        self._workers = workers
        self.events: list[str] = []
        self._settings: PageSettings | None = None

    # Properties, as 026's pool may expose them: the Protocol only reads them.
    @property
    def backlog(self) -> int:
        return 0

    @property
    def workers(self) -> int:
        return self._workers

    async def start(self, settings: PageSettings) -> None:
        self.events.append(f"start {settings.scope.seed_hosts[0]}")
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        self.events.append(f"prepare {url}")
        assert self._settings is not None
        return prepare_page(url, response, self._settings)

    async def close(self) -> None:
        self.events.append("close")


def test_the_page_executor_starts_once_before_the_seed_and_closes_at_the_end(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(TWO_PAGES)
    executor = RecordingExecutor()

    crawl_result(server.url("/"), pages=lambda: executor)

    assert executor.events == [
        "start 127.0.0.1",
        f"prepare {server.url('/')}",
        f"prepare {server.url('/a')}",
        "close",
    ]


def _failing(message: str) -> Callable[[PassContext], Awaitable[None]]:
    async def run(context: PassContext) -> None:
        raise RuntimeError(message)

    return run


def test_the_page_executor_closes_when_the_crawl_fails(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(TWO_PAGES)
    executor = RecordingExecutor()
    hooks = Hooks(passes=(Pass("failing", _failing("the pass failed")),))

    with pytest.raises(RuntimeError, match="the pass failed"):
        crawl_result(server.url("/"), hooks, pages=lambda: executor)

    assert executor.events[-1:] == ["close"]


def test_crawl_started_reports_the_workers_of_the_page_executor(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(TWO_PAGES)
    reporter = Collected()

    crawl_result(server.url("/"), pages=lambda: RecordingExecutor(workers=3), reporter=reporter)

    assert [data["parse_workers"] for name, data in reporter.events if name == "crawl_started"] == [
        3
    ]


class FailingStartReporter:
    """A reporter whose crawl_started event fails, as a closed stderr would."""

    def warn(self, diagnostic: Diagnostic) -> None:
        pass

    def event(self, name: str, **data: Any) -> None:
        if name == "crawl_started":
            raise OSError("stderr is closed")


def test_the_page_executor_closes_when_the_start_event_fails(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(TWO_PAGES)
    executor = RecordingExecutor()

    with pytest.raises(OSError, match="stderr is closed"):
        crawl_result(server.url("/"), pages=lambda: executor, reporter=FailingStartReporter())

    assert executor.events == ["close"]


class CrashingExecutor:
    """Prepares nothing, as 026's pool reports a worker that ended while it held a Page."""

    backlog = 0
    workers = 0

    async def start(self, settings: PageSettings) -> None:
        pass

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        return PreparedPage(parse_error="worker_crashed", parse_error_message="worker 1 ended")

    async def close(self) -> None:
        pass


def test_a_page_whose_preparation_failed_keeps_the_links_of_its_headers(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<a href="/a">A</a>',
                    headers=[("Link", "</c>; rel=canonical"), ("Refresh", "5; url=/r")],
                )
            }
        )
    )

    result = crawl_result(server.url("/"), pages=CrashingExecutor)

    assert (
        query(
            result.crawl_file,
            "SELECT url, parsed, parse_error, discovered_via FROM urls ORDER BY id",
        ),
        [(warning.code, "worker_crashed" in warning.message) for warning in result.warnings],
    ) == (
        [
            (server.url("/"), 0, "worker_crashed", "seed"),
            (server.url("/c"), 0, None, "canonical"),
            (server.url("/r"), 0, None, "http_refresh"),
        ],
        [("parse_failed", True)],
    )


def test_a_preparation_that_gave_nothing_names_no_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/boom">Boom</a>')}))

    result = crawl_result(server.url("/"), pages=CrashingExecutor)

    ((code, details),) = [
        (warning["code"], warning["details"]) for warning in result.to_json()["warnings"]
    ]
    assert (code, sorted(details)) == ("parse_failed", ["count", "first_url"])


class SlowPool:
    """A parse pool that takes 10 s per Page and holds two Pages beyond the requests."""

    backlog = 2
    workers = 1

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._settings: PageSettings | None = None
        self._preparing = 0
        self.most_preparing = 0

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        assert self._settings is not None
        self._preparing += 1
        self.most_preparing = max(self.most_preparing, self._preparing)
        try:
            await self._clock.sleep(10)
            return prepare_page(url, response, self._settings)
        finally:
            self._preparing -= 1

    async def close(self) -> None:
        pass


def test_fetching_waits_while_page_preparation_is_behind_by_its_backlog(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(30))),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in range(30)},
    }
    fetcher = FakeFetcher(clock, pages)
    pool = SlowPool(clock)

    crawl_result("http://site.test/", pages=lambda: pool, clock=clock, fetcher=fetcher)

    # The global cap of 20 at the default concurrency, plus the pool's backlog of 2.
    assert (pool.most_preparing, len(fetcher.starts)) == (22, 32)


class RaisingExecutor:
    """Page preparation in process that breaks an invariant of its own for `/broken`, as a pool
    raises "cannot schedule new futures after shutdown" when it is used after its close."""

    backlog = 0
    workers = 0

    def __init__(self) -> None:
        self.prepared: list[str] = []
        self._settings: PageSettings | None = None

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        self.prepared.append(url)
        if url.endswith("/broken"):
            raise RuntimeError("cannot schedule new futures after shutdown")
        assert self._settings is not None
        return prepare_page(url, response, self._settings)

    async def close(self) -> None:
        pass


def test_a_url_whose_preparation_raises_ends_the_crawl_while_its_depth_is_dispatched(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    slow = [f"/s{n}" for n in range(30)]
    pages = {
        "/": FakePage("".join(f'<a href="{path}">L</a>' for path in ["/broken", *slow])),
        "/broken": FakePage("<p>B</p>"),
        **{path: FakePage("<p>S</p>", delay=1) for path in slow},
    }
    executor = RaisingExecutor()
    fetcher = FakeFetcher(clock, pages)

    # 31 URLs over a task bound of 20: the dispatcher waits for room until /broken has failed.
    with pytest.raises(RuntimeError, match="after shutdown"):
        crawl_result("http://site.test/", clock=clock, fetcher=fetcher, pages=lambda: executor)
    (crawl_file,) = temp_workspace.home.rglob("*.sqlite")

    # The room /broken freed goes to /s19 before its failure is seen; like a stop, the failure
    # then lets none of the URLs still waiting for room start.
    started = {path for path, _ in fetcher.path_starts}
    assert (
        executor.prepared.count("http://site.test/broken"),
        started & set(slow[20:]),
        crawl_row(crawl_file)["state"],
    ) == (1, set(), "running")


def test_a_checked_url_whose_preparation_raises_ends_the_crawl_before_the_sweep(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # An image URL that answers with an HTML page, as a soft 404 does, is prepared as one.
    pages = {
        "/": FakePage('<img src="/broken"><a href="/slow">S</a>'),
        "/broken": FakePage("<p>Not found</p>"),
        "/slow": FakePage("<p>S</p>", delay=1),
    }
    executor = RaisingExecutor()

    # /broken fails while the depth waits a second for /slow, before the sweep waits on it.
    with pytest.raises(RuntimeError, match="after shutdown"):
        crawl_result(
            "http://site.test/",
            clock=clock,
            fetcher=FakeFetcher(clock, pages),
            pages=lambda: executor,
        )
    (crawl_file,) = temp_workspace.home.rglob("*.sqlite")

    assert (executor.prepared.count("http://site.test/broken"), crawl_row(crawl_file)["state"]) == (
        1,
        "running",
    )
