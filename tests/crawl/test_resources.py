"""Resources: requested, never parsed unless in-Scope HTML (020-add-crawl-core D5; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_an_image_is_checked_but_not_parsed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/logo.png">'),
                "/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT status_code, parsed FROM urls WHERE url = ?", [server.url("/logo.png")]
    ) == [(200, 0)]
