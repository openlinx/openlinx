"""The page executor's lifecycle, through the Crawl Service (020-add-crawl-core D9; seam 3)."""

from collections.abc import Awaitable, Callable

import pytest

from spider.crawl.fetcher import FetchResult
from spider.crawl.hooks import Hooks, Pass
from spider.crawl.pages import PageSettings, PreparedPage, prepare_page
from spider.crawl.urls import NormalizedUrl
from spider.output.reporter import Collected
from spider.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
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


def _failing(message: str) -> Callable[[CrawlWriter], Awaitable[None]]:
    async def run(writer: CrawlWriter) -> None:
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
