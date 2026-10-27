"""Compressed responses (022-add-fetch-policy, fetching; seam 3)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.crawling import crawled
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
