"""Continuing a stopped or failed Crawl (020-add-crawl-core D20; seam 2)."""

import json
from dataclasses import replace

import msgspec
from selectolax.lexbor import LexborHTMLParser

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
