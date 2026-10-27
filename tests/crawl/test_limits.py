"""Response size and URL length limits (022-add-fetch-policy, fetching; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import LargeFile, Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

MIB = 1024 * 1024


def test_a_huge_page_is_not_parsed(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/huge.html">Catalogue</a>'),
                "/huge.html": LargeFile(size=25 * MIB, content_type="text/html"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, body_truncated, parsed, parse_error, size_bytes, "
        "transferred_bytes > 20 * 1024 * 1024 FROM urls WHERE url = ?",
        [server.url("/huge.html")],
    ) == [("fetched", 1, 0, "body_too_large", None, 1)]


def test_a_very_long_url_is_skipped(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # A faceted search that writes every filter into the path.
    long_path = "/" + "a" * 2001
    server = fixture_site(
        Site(
            {
                "/": Page(body=f'<title>Shop</title><a href="{long_path}">All filters</a>'),
                long_path: Page(body="<title>Filtered</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, skip_reason, is_internal, in_scope FROM urls WHERE url = ?",
        [server.url(long_path)],
    ) == [("skipped", "url_too_long", 1, 0)]
