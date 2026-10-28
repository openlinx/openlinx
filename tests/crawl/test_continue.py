"""Continuing a stopped or failed Crawl (020-add-crawl-core D20; seam 2)."""

import json

from spider.services.crawling import CrawlOverrides
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
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
