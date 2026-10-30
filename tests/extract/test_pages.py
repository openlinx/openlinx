"""Page rows (030-add-page-data, page-data; seam 3+6)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import select

from openlinx.crawl.pages.preparation import Extractor, PageInput, extractor
from openlinx.extract.page_data import PAGE_DATA, PageData
from openlinx.extract.page_links import PAGE_LINKS, PageLinks
from openlinx.services.hooks import default_hooks
from openlinx.store.schema import public_tables
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
                # Answers only once /x is requested, so it can lower /x only in flight.
                "/late.html": Page(body='<a href="/x">X</a>', after="/x"),
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


def test_a_crawled_page_stores_its_directives_canonicals_and_pagination(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # The page_row helper of the seam-4 tests copies how the crawl engine assembles a URL's
    # result; this reads the same columns from a real Crawl.
    server = fixture_site(
        Site(
            routes={
                "/list/2": Page(
                    body='<html><head><title>Page 2</title><link rel="canonical" href="/list">'
                    '<link rel="prev" href="/list/1"><meta name="robots" content="noindex">'
                    "</head><body><p>Items 11-20</p></body></html>",
                    headers=(
                        ("Link", '</list>; rel="canonical", </list/3>; rel="next"'),
                        ("Refresh", "0; url=/list"),
                    ),
                ),
                "/list": Page(body="<p>All items</p>"),
                "/list/1": Page(body="<p>Items 1-10</p>"),
                "/list/3": Page(body="<p>Items 21-30</p>"),
            }
        )
    )

    crawl_file = crawl_result(server.url("/list/2")).crawl_file

    assert query(
        crawl_file,
        "SELECT redirect_type, redirect_url, meta_robots_noindex, canonical_url, canonical_count,"
        " rel_prev_1, http_rel_next_1 FROM pages WHERE address = ?",
        [server.url("/list/2")],
    ) == [
        (
            "http_refresh",
            server.url("/list"),
            1,
            server.url("/list"),
            2,
            server.url("/list/1"),
            server.url("/list/3"),
        )
    ]


def _failing_page_data(tree: LexborHTMLParser, page: PageInput, config: None) -> PageData:
    raise RuntimeError("Page extractor bug")


def _failing_page_links(tree: LexborHTMLParser, page: PageInput, config: None) -> PageLinks:
    raise RuntimeError("Link extractor bug")


def test_a_page_whose_page_extractor_failed_keeps_its_response_data_and_links(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/broken": Page(
                    body='<title>T</title><meta name="robots" content="noindex"><a href="/a">A</a>'
                ),
                "/a": Page(body="<p>A</p>"),
            }
        )
    )
    broken = server.url("/broken")
    failing: dict[str, Extractor[Any, Any]] = {
        PAGE_DATA.name: extractor(PAGE_DATA.name, _failing_page_data, None),
        PAGE_LINKS.name: extractor(PAGE_LINKS.name, _failing_page_links, None),
    }
    defaults = default_hooks()
    hooks = replace(
        defaults,
        extractors=tuple(failing.get(built.name, built) for built in defaults.extractors),
    )

    crawl_file = crawl_result(broken, hooks).crawl_file

    assert query(
        crawl_file,
        "SELECT urls.parsed, urls.parse_error, pages.status_code, title_1, meta_robots_noindex,"
        " indexability, outlinks FROM pages JOIN urls ON urls.id = pages.url_id WHERE address = ?",
        [broken],
    ) == [(1, "extractor_error", 200, None, 1, "non_indexable", 1)]
    assert query(
        crawl_file,
        "SELECT target.url, links.type, links.anchor_text FROM links"
        " JOIN urls AS source ON source.id = links.source_url_id"
        " JOIN urls AS target ON target.id = links.target_url_id WHERE source.url = ?",
        [broken],
    ) == [(server.url("/a"), "hyperlink", None)]
