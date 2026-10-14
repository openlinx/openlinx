"""The frontier's invariants: one request per URL, an end, and the order (020 D1; seam 3)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
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
