"""Page rows (030-add-page-data, page-data; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_html_response_becomes_a_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/about": Page(body="<p>About</p>")}))

    crawl_file = crawl_result(server.url("/about")).crawl_file

    assert query(crawl_file, "SELECT address FROM pages") == [(server.url("/about"),)]
