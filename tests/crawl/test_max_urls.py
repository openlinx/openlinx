"""The URL limit over HTTP (020-add-crawl-core D7, crawling; seam 3 and 3+6)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.sites import NINE_PAGES
from tests.support.workspace import TempWorkspace


def test_urls_not_requested_stay_queued(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    crawl_file = crawled(server.url("/"), "--max-urls", "3")

    assert query(crawl_file, "SELECT count(*) FROM urls WHERE fetch_state = 'queued'") == [(7,)]


@pytest.mark.slow
def test_the_limit_holds_under_concurrency(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body="".join(f'<a href="/slow/{n}">S</a>' for n in range(1, 21))),
                **{f"/slow/{n}": Page(body="<p>S</p>", delay=0.5) for n in range(1, 21)},
            }
        )
    )

    crawled(server.url("/"), "--max-urls", "5", "--concurrency", "5")

    assert len([request for request in server.requests if request.path != "/robots.txt"]) == 5
