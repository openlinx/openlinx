"""Spider mode over HTTP (020-add-crawl-core, crawling; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site(routes={"/": Page(body="<html><body><h1>Home</h1></body></html>")})


def test_the_seed_is_fetched_and_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT host, fetch_state, status_code, crawl_depth, discovered_via FROM urls "
        "WHERE url = ?",
        [server.url("/")],
    ) == [("127.0.0.1", "fetched", 200, 0, "seed")]


def test_the_request_is_for_the_recorded_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)

    crawl_file = crawled(server.url("/?q=%2F"))
    (url,) = query(crawl_file, "SELECT url FROM urls")[0]

    assert [server.url(request.path) for request in server.requests] == [url]


def test_the_seed_is_kept_as_given_in_seeds(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)

    crawl_file = crawled(server.base_url)

    assert (
        query(crawl_file, "SELECT position, url FROM seeds"),
        query(crawl_file, "SELECT url FROM urls"),
    ) == ([(1, server.base_url)], [(server.url("/"),)])


def test_pages_linked_from_the_seed_are_crawled(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/about">About</a>'),
                "/about": Page(body='<a href="/team">Team</a>'),
                "/team": Page(body="<p>Team</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert sorted(query(crawl_file, "SELECT url, fetch_state, status_code FROM urls")) == [
        (server.url("/"), "fetched", 200),
        (server.url("/about"), "fetched", 200),
        (server.url("/team"), "fetched", 200),
    ]


def test_a_discovered_url_points_to_where_it_was_found(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/about">About</a>')}))

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT found.discovered_via, source.url FROM urls AS found "
        "JOIN urls AS source ON source.id = found.found_on_url_id WHERE found.url = ?",
        [server.url("/about")],
    ) == [("hyperlink", server.url("/"))]
