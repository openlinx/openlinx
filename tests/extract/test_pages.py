"""Page rows (030-add-page-data, page-data; seam 3+6)."""

from datetime import UTC, datetime

from sqlalchemy import select

from spider.store.schema import public_tables
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


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


def test_crawl_timestamp_repeats_fetched_at(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/about": Page(body="<p>About</p>")}))
    clock = FakeClock(start=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))

    crawl_file = crawl_result(server.url("/about"), clock=clock).crawl_file

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


def test_cookie_values_are_not_stored_in_page_data(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/cookie": Page(body="<p>Cookie</p>", headers=[("Set-Cookie", "sid=abc123")])})
    )

    crawl_file = crawl_result(server.url("/cookie")).crawl_file

    # Every table of this change, so the tables of later groups are searched too.
    tables = [table for table in public_tables() if table.info["change"] == 30]
    holding_the_value = [
        table.name
        for table in tables
        for row in query(crawl_file, str(select(table)))
        if any(isinstance(value, str) and "abc123" in value for value in row)
    ]
    assert (query(crawl_file, "SELECT name FROM cookies"), holding_the_value) == ([("sid",)], [])


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
