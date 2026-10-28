"""Continuing a stopped or failed Crawl (020-add-crawl-core D20; seam 2)."""

import json
import socket
from collections.abc import Sequence
from dataclasses import replace

import msgspec
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection, text

from spider.crawl.engine.hooks import Pass, PassContext, UrlResult, handler
from spider.crawl.pages.preparation import PageInput, extractor
from spider.services.crawling import CrawlOverrides
from spider.services.hooks import default_hooks
from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

_PAGES = range(1, 10)
NINE_PAGES = Site(
    routes={
        "/": Page(body="".join(f'<a href="/p{n}">P{n}</a>' for n in _PAGES)),
        **{f"/p{n}": Page(body=f"<p>{n}</p>") for n in _PAGES},
    }
)


def test_continuing_a_stopped_crawl_completes_it(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    stopped = crawl_result(server.url("/"), max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=None))

    assert (
        stopped.summary.stop_reason,
        result.summary.state,
        query(result.crawl_file, "SELECT count(*) FROM urls WHERE fetch_state = 'fetched'"),
    ) == ("max_urls", "completed", [(10,)])


def test_a_continue_records_the_settings_it_runs_with(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    stopped = crawl_result(server.url("/"), max_urls=3, concurrency=2)

    result = continued(stopped, CrawlOverrides(max_urls=None, rate=50.0))

    # The file says what the last run used, the settings left out kept as they were.
    (config,) = query(result.crawl_file, "SELECT config FROM crawl")
    recorded = json.loads(config[0])["crawl"]
    assert (recorded["max_urls"], recorded["rate"], recorded["concurrency"]) == (None, 50.0, 2)


def test_the_url_limit_counts_over_the_crawls_whole_life(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    stopped = crawl_result(server.url("/"), max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=5))

    assert (
        query(result.crawl_file, "SELECT count(*) FROM urls WHERE fetch_state = 'fetched'"),
        result.summary.state,
        result.summary.stop_reason,
    ) == ([(5,)], "stopped", "max_urls")


def test_warnings_cover_the_crawls_whole_life(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # a.site.test and b.site.test share an instance whose robots.txt answers 503. / links to
    # a.site.test first, so the first run meets it; /p5, which only the continue fetches, links
    # to a.site.test again and to b.site.test.
    links = '<a href="http://a.site.test/a">A</a>' + "".join(
        f'<a href="/p{n}">P{n}</a>' for n in range(1, 6)
    )
    seed_site = Site(
        routes={
            "/": Page(body=links),
            **{f"/p{n}": Page(body=f"<p>{n}</p>") for n in range(1, 5)},
            "/p5": Page(
                body='<a href="http://a.site.test/c">C</a><a href="http://b.site.test/b">B</a>'
            ),
        }
    )
    seed, down = fixture_site(seed_site), fixture_site(Site(routes={"/robots.txt": Status(503)}))
    resolver = FixtureResolver({"site.test": seed, "a.site.test": down, "b.site.test": down})
    stopped = crawl_result("http://site.test/", resolver=resolver, scope="subdomains", max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=None), resolver=resolver)

    # Once per host over the Crawl's life, and the first run's max_urls_reached is gone.
    (stored,) = query(result.crawl_file, "SELECT warnings FROM crawl")
    assert (
        stopped.summary.stop_reason,
        [(w["code"], w["details"]["host"]) for w in json.loads(stored[0])],
        [(w.code, w.details["host"]) for w in result.warnings],
    ) == (
        "max_urls",
        [("robots_unreachable", "a.site.test"), ("robots_unreachable", "b.site.test")],
        [("robots_unreachable", "a.site.test"), ("robots_unreachable", "b.site.test")],
    )


class Heading(msgspec.Struct, frozen=True):
    text: str


def _failing_on_pages(tree: LexborHTMLParser, page: PageInput, config: None) -> Heading:
    if "/p" in page.url:
        raise ValueError(page.url)
    return Heading(page.url)


def test_a_counted_warning_adds_up_over_the_crawls_whole_life(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    hooks = default_hooks()
    hooks = replace(hooks, extractors=(*hooks.extractors, extractor("h", _failing_on_pages, None)))
    stopped = crawl_result(server.url("/"), hooks, max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=None), hooks)

    # /p1 and /p2 failed in the first run and /p3 to /p9 in the continue: one warning.
    assert [(w.code, w.details["count"], w.details["first_url"]) for w in result.warnings] == [
        ("parse_failed", 9, server.url("/p1"))
    ]


def test_continuing_does_not_request_fetched_urls_again(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    stopped = crawl_result(server.url("/"), max_urls=3)
    fetched = {
        url
        for (url,) in query(
            stopped.crawl_file, "SELECT url FROM urls WHERE fetch_state = 'fetched'"
        )
    }
    before = len(server.requests)

    continued(stopped, CrawlOverrides(max_urls=None))

    again = [r.path for r in server.requests[before:] if server.url(r.path) in fetched]
    assert (len(fetched), again) == (3, [])


def _url_of(result: UrlResult) -> tuple[str, ...]:
    return (result.url,)


def _write_crawl_row(connection: Connection, urls: Sequence[str]) -> None:
    # Read inside the unit of each URL the continue records, after its own unit was flushed.
    state, stop_reason = connection.execute(text("SELECT state, stop_reason FROM crawl")).one()
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_crawl_row (state, stop_reason)"))
    connection.execute(
        text("INSERT INTO test_crawl_row VALUES (:state, :stop_reason)"),
        {"state": state, "stop_reason": stop_reason},
    )


def test_continuing_clears_how_the_crawl_ended(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    hooks = default_hooks()
    hooks = replace(
        hooks, handlers=(*hooks.handlers, handler("crawl_row", _url_of, _write_crawl_row))
    )
    stopped = crawl_result(server.url("/"), max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=None), hooks)

    assert (
        stopped.summary.state,
        query(result.crawl_file, "SELECT DISTINCT state, stop_reason FROM test_crawl_row"),
    ) == ("stopped", [("running", None)])


def _free_port() -> int:
    """A port nothing listens on, until the test starts a site there."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def test_a_failed_crawl_is_continued_once_its_seed_answers(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    port = _free_port()
    seed = f"http://127.0.0.1:{port}/"
    failed = crawl_result(seed, network_wait=0)
    fixture_site(NINE_PAGES, port=port)

    result = continued(failed)

    assert (
        failed.summary.stop_reason,
        result.summary.state,
        query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", [seed]),
    ) == ("seed_unreachable", "completed", [("fetched",)])


def test_a_continue_requests_the_urls_an_unreachable_robots_txt_blocked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    links = '<a href="http://other.test/a">A</a>' + "".join(
        f'<a href="/p{n}">P{n}</a>' for n in _PAGES
    )
    pages = {f"/p{n}": Page(body=f"<p>{n}</p>") for n in _PAGES}
    seed = fixture_site(Site(routes={"/": Page(body=links), **pages}))
    # other.test answers robots.txt with 503 in the first run, and has none by the continue.
    down = fixture_site(Site(routes={"/robots.txt": Status(503)}))
    up = fixture_site(Site(routes={"/a": Page(body="<p>A</p>")}))
    stopped = crawl_result(
        "http://site.test/",
        resolver=FixtureResolver({"site.test": seed, "other.test": down}),
        max_urls=3,
    )
    blocked = query(
        stopped.crawl_file, "SELECT skip_reason FROM urls WHERE url = 'http://other.test/a'"
    )

    result = continued(
        stopped,
        CrawlOverrides(max_urls=None),
        resolver=FixtureResolver({"site.test": seed, "other.test": up}),
    )

    assert (
        blocked,
        query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url = 'http://other.test/a'"),
    ) == ([("robots_unreachable",)], [("fetched",)])


def test_post_crawl_passes_run_again_after_a_continue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)
    runs: list[int] = []

    async def count_runs(context: PassContext) -> None:
        runs.append(len(runs) + 1)

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("count_runs", count_runs)))
    stopped = crawl_result(server.url("/"), hooks, max_urls=3)

    result = continued(stopped, CrawlOverrides(max_urls=None), hooks)

    # Once as the first run stopped, and once more as the continue completed.
    assert (stopped.summary.state, result.summary.state, runs) == ("stopped", "completed", [1, 2])
