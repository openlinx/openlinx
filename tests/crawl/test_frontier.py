"""The frontier: one request per URL, an end, and the order (020-add-crawl-core D1; seam 3)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row
from tests.support.workspace import TempWorkspace


def _links_to_all_but(page: int) -> str:
    others = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 11) if n != page)
    return others + '<a href="/">Home</a>'


def test_each_url_is_requested_once(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/p1">P1</a>'),
                **{f"/p{n}": Page(body=_links_to_all_but(n)) for n in range(1, 11)},
            }
        )
    )

    crawled(server.url("/"))

    paths = [request.path for request in server.requests]
    expected = ["/", *(f"/p{n}" for n in range(1, 11))]
    assert {path: paths.count(path) for path in expected} == dict.fromkeys(expected, 1)


def test_a_link_cycle_ends(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a>'),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body='<a href="/a">A</a><a href="/">Home</a>'),
            }
        )
    )

    assert crawl_row(crawled(server.url("/")))["state"] == "completed"


def test_followed_urls_start_in_discovery_order(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/c">C</a><a href="/a">A</a><a href="/b">B</a>'),
                **{path: Page(body="<p>Page</p>") for path in ("/c", "/a", "/b")},
            }
        )
    )

    crawled(server.url("/"), "--concurrency", "1")

    assert [request.path for request in server.requests if request.path in {"/a", "/b", "/c"}] == [
        "/c",
        "/a",
        "/b",
    ]
