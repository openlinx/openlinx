"""The URL limit over HTTP (020-add-crawl-core D7, crawling; seam 3 and 3+6)."""

from tests.fixture_site.plugin import StartSite
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
