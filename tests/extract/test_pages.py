"""Page rows (030-add-page-data, page-data; seam 3+6)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from spider.store.schema import public_tables
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site, Status
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

# Long against the few milliseconds a local request takes, short for a test.
SLOW = 2.0


def test_html_response_becomes_a_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/about": Page(body="<p>About</p>")}))

    crawl_file = crawl_result(server.url("/about")).crawl_file

    assert query(crawl_file, "SELECT address FROM pages") == [(server.url("/about"),)]


def test_error_page_keeps_response_data(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/missing">Missing</a>'),
                "/missing": Status(404, body="<title>Not found</title>"),
            }
        )
    )
    missing = server.url("/missing")

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(
        crawl_file, "SELECT status_code, title_1 FROM pages WHERE address = ?", [missing]
    ) == [(404, None)]


def test_crawl_timestamp_repeats_fetched_at(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock(start=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    fetcher = FakeFetcher(clock, {"/about": FakePage("<p>About</p>")})

    crawl_file = crawl_result("http://site.test/about", clock=clock, fetcher=fetcher).crawl_file

    assert query(crawl_file, "SELECT crawl_timestamp FROM pages") == [("2026-01-02T03:04:05.000Z",)]


def test_crawl_depth_is_copied_from_the_crawl_engine(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/l1">1</a>'),
                "/l1": Page(body='<a href="/l2">2</a>'),
                "/l2": Page(body="<p>Two</p>"),
            }
        )
    )

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(
        crawl_file, "SELECT crawl_depth FROM pages WHERE address = ?", [server.url("/l2")]
    ) == [(2,)]


def test_repeated_values_equal_the_urls_row(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/about": Page(body="<p>About</p>")}))
    about = server.url("/about")

    crawl_file = crawl_result(about).crawl_file

    assert query(
        crawl_file,
        "SELECT content_type, status_code, response_time_ms, crawl_depth, crawl_timestamp "
        "FROM pages WHERE address = ?",
        [about],
    ) == query(
        crawl_file,
        "SELECT content_type, status_code, response_time_ms, crawl_depth, fetched_at "
        "FROM urls WHERE url = ?",
        [about],
    )


@pytest.mark.slow
def test_a_page_lowered_in_flight_has_the_depth_of_its_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
                "/late.html": Page(body='<a href="/x">X</a>', delay=SLOW / 2),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body='<a href="/x">X</a>'),
                # In flight at depth 3 when the late check lowers it to 2.
                "/x": Page(body="<p>X</p>", delay=SLOW),
            }
        )
    )

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(
        crawl_file,
        "SELECT pages.crawl_depth, urls.crawl_depth FROM pages JOIN urls ON urls.id = pages.url_id "
        "WHERE pages.address = ?",
        [server.url("/x")],
    ) == [(2, 2)]


def test_cookie_values_are_not_stored_in_page_data(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/cookie": Page(
                    body="<p>Cookie</p>",
                    headers=[
                        (
                            "Set-Cookie",
                            "PHPSESSID=9c7f3b2e1d4a8f6e0b5c3a7d9e1f2b4c; path=/; HttpOnly",
                        )
                    ],
                )
            }
        )
    )

    crawl_file = crawl_result(server.url("/cookie")).crawl_file

    # Every table of this change, so the tables of later groups are searched too.
    tables = [table for table in public_tables() if table.info["change"] == 30]
    holding_the_value = [
        table.name
        for table in tables
        for row in query(crawl_file, str(select(table)))
        if any(
            isinstance(value, str) and "9c7f3b2e1d4a8f6e0b5c3a7d9e1f2b4c" in value for value in row
        )
    ]
    assert (query(crawl_file, "SELECT name FROM cookies"), holding_the_value) == (
        [("PHPSESSID",)],
        [],
    )


def test_cookies_of_a_redirect_are_stored(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A login that sets the session cookie and sends the browser home.
    redirect = Redirect(
        location="/",
        status=302,
        content_type="text/html",
        headers=[
            (
                "Set-Cookie",
                "session=eyJ1c2VyX2lkIjo0Mn0.Zx8kVQ.q3Jt0mXb; "
                "Path=/; HttpOnly; Secure; SameSite=Lax",
            )
        ],
    )
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/login">Log in</a>'), "/login": redirect})
    )
    login = server.url("/login")

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert query(
        crawl_file,
        "SELECT pages.set_cookie_count, cookies.name, cookies.http_only, cookies.same_site "
        "FROM pages JOIN cookies USING (url_id) WHERE pages.address = ?",
        [login],
    ) == [(1, "session", 1, "lax")]


def test_image_response_is_not_a_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/logo.png">Logo</a>'),
                "/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )
    logo = server.url("/logo.png")

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert (
        query(crawl_file, "SELECT fetch_state, content_type FROM urls WHERE url = ?", [logo]),
        query(crawl_file, "SELECT url_id FROM pages WHERE address = ?", [logo]),
    ) == ([("fetched", "image/png")], [])


def test_external_html_response_is_not_a_page(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site(routes={"/page": Page(body="<p>Page</p>")}),
    )
    other = "http://other.test/page"

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(crawl_file, "SELECT fetch_state, is_internal FROM urls WHERE url = ?", [other]),
        query(crawl_file, "SELECT url_id FROM pages WHERE address = ?", [other]),
    ) == ([("fetched", 0)], [])
