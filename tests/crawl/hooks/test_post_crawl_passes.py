"""Verify when post-Crawl Passes run and what context they receive."""

from dataclasses import replace

from openlinx.clock import Clock
from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext
from openlinx.store.crawls import crawl_summary
from openlinx.store.records import CrawlState
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.network import closed_port
from tests.support.sites import NINE_PAGES
from tests.support.workspace import TempWorkspace


def test_post_crawl_passes_run_before_a_crawl_is_completed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    seen: list[CrawlState] = []

    async def record_state(context: PassContext) -> None:
        seen.append((await context.writer.run_async(crawl_summary())).state)

    hooks = Hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("state", record_state)))

    crawl_result(server.url("/"), hooks)

    assert seen == ["running"]


def test_post_crawl_passes_run_in_the_order_the_hooks_declare(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    ran: list[str] = []

    async def first(context: PassContext) -> None:
        ran.append("first")

    async def second(context: PassContext) -> None:
        ran.append("second")

    hooks = Hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("first", first), Pass("second", second)))

    crawl_result(server.url("/"), hooks)

    assert ran == ["first", "second"]


def test_a_post_crawl_pass_gets_the_clock_of_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>Home</p>")})
    clocks: list[Clock] = []

    async def record_the_clock(context: PassContext) -> None:
        clocks.append(context.clock)

    hooks = Hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("clock", record_the_clock)))

    crawl_result("http://site.test/", hooks, clock=clock, fetcher=fetcher)

    assert clocks == [clock]


def test_post_crawl_passes_run_when_the_url_limit_stops_a_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    runs: list[str] = []

    async def count_runs(context: PassContext) -> None:
        runs.append("run")

    hooks = Hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("count", count_runs)))

    crawl_result(server.url("/"), hooks, max_urls=3)

    assert runs == ["run"]


def test_post_crawl_passes_do_not_run_for_a_failed_crawl(temp_workspace: TempWorkspace) -> None:
    runs: list[str] = []

    async def count_runs(context: PassContext) -> None:
        runs.append("run")

    hooks = Hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("count", count_runs)))

    result = crawl_result(f"http://127.0.0.1:{closed_port()}/", hooks, network_wait=0)

    assert (result.summary.state, runs) == ("failed", [])
