"""Compressed responses (022-add-fetch-policy, fetching; seam 3)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.fixture_site.sites.exact import site as exact
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

SHOP = Site(
    {
        "/robots.txt": Robots("User-agent: *\nDisallow: /cart\n"),
        "/": Page(body='<title>Shop</title><a href="/shoes">Shoes</a>'),
        "/shoes": Page(body="<title>Shoes</title>"),
    }
)


def test_requests_accept_compressed_bodies(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SHOP)

    crawled(server.url("/"))

    assert {
        request.path: request.headers.get("Accept-Encoding") for request in server.requests
    } == {
        "/robots.txt": "gzip, deflate, br",
        "/": "gzip, deflate, br",
        "/shoes": "gzip, deflate, br",
    }


def test_a_compressed_resource_records_both_sizes(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            root=exact.SITE.root,
            routes={
                "/": Page(body='<title>Shop</title><script src="/app.js"></script>'),
                "/app.js": exact.SITE.routes["/app.js"],
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT size_bytes, transferred_bytes, content_encoding FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [(10000, 2500, "gzip")]
