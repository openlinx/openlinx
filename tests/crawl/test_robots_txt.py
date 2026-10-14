"""robots.txt over HTTP (020-add-crawl-core D6, crawling; seam 3 and 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
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


# /robots.txt disallows /private/, which / links to.
PRIVATE_SITE = Site(
    routes={
        "/robots.txt": Robots("User-agent: *\nDisallow: /private/\n"),
        "/": Page(body='<a href="/private/a">A</a>'),
        "/private/a": Page(body="<p>A</p>"),
    }
)


def test_a_disallowed_url_is_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawled(server.url("/"))

    assert [request.path for request in server.requests if request.path == "/private/a"] == []


def test_a_disallowed_url_is_recorded_as_blocked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT skip_reason, blocked_by_robots_txt FROM urls WHERE url = ?",
        [server.url("/private/a")],
    ) == [("blocked_by_robots_txt", 1)]


def test_a_requested_url_is_allowed_and_a_url_skipped_before_robots_txt_is_unchecked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"), "--exclude", "/private/")

    assert query(crawl_file, "SELECT url, blocked_by_robots_txt FROM urls ORDER BY id") == [
        (server.url("/"), 0),
        (server.url("/private/a"), None),
    ]
