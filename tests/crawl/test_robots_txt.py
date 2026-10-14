"""robots.txt over HTTP (020-add-crawl-core D6, crawling; seam 3 and 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.support.crawling import crawled
from tests.support.sites import NINE_PAGES
from tests.support.workspace import TempWorkspace


def test_robots_txt_is_fetched_once_per_origin(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    crawled(server.url("/"))

    assert [request.path for request in server.requests if request.path == "/robots.txt"] == [
        "/robots.txt"
    ]
