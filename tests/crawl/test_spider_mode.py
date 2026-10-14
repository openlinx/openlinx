"""Spider mode over HTTP (020-add-crawl-core, crawling; seam 3+6)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row, query
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


def test_a_completed_crawl_records_its_state(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)

    row = crawl_row(crawled(server.url("/")))

    assert (row["state"], row["stop_reason"]) == ("completed", None)


@pytest.mark.slow
def test_response_timing_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/slow">Slow</a>'), "/slow": Page(body="", delay=0.5)})
    )

    crawl_file = crawled(server.url("/"))
    ((response_time_ms, fetched_at),) = query(
        crawl_file,
        "SELECT response_time_ms, fetched_at FROM urls WHERE url = ?",
        [server.url("/slow")],
    )

    assert (response_time_ms >= 500, fetched_at is not None) == (True, True)


def test_the_content_type_is_recorded_as_received(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/doc.pdf">Doc</a>'),
                "/doc.pdf": Page(body="%PDF-1.7", content_type="application/pdf"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT content_type FROM urls WHERE url = ?", [server.url("/doc.pdf")]
    ) == [("application/pdf",)]


def test_a_response_that_is_not_html_is_not_parsed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/doc.pdf">Doc</a>'),
                "/doc.pdf": Page(body='<a href="/hidden">x</a>', content_type="application/pdf"),
                "/hidden": Page(body="<p>Hidden</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert sorted(query(crawl_file, "SELECT url, parsed FROM urls")) == [
        (server.url("/"), 1),
        (server.url("/doc.pdf"), 0),
    ]


LOGOUT_LINK = Site(
    routes={"/": Page(body='<a href="/logout">Log out</a>'), "/logout": Page(body="<p>Bye</p>")}
)


def test_an_excluded_url_is_never_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LOGOUT_LINK)

    crawled(server.url("/"), "--exclude", "/logout$")

    assert [request.path for request in server.requests] == ["/"]


def test_an_excluded_url_is_recorded_as_skipped(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LOGOUT_LINK)

    crawl_file = crawled(server.url("/"), "--exclude", "/logout$")

    assert query(
        crawl_file,
        "SELECT fetch_state, skip_reason FROM urls WHERE url = ?",
        [server.url("/logout")],
    ) == [("skipped", "excluded")]


def test_a_skipped_url_has_no_response_data(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LOGOUT_LINK)

    crawl_file = crawled(server.url("/"), "--exclude", "/logout$")

    assert query(
        crawl_file,
        "SELECT status_code, content_type, response_time_ms, fetched_at, parsed FROM urls "
        "WHERE url = ?",
        [server.url("/logout")],
    ) == [(None, None, None, None, 0)]


def test_deeply_nested_html_does_not_stop_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # 10,000 deep: lexbor's tree builder parses it in about 50 ms (design Risks).
    nested = "<div>" * 10_000 + '<a href="/after">After</a>' + "</div>" * 10_000
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/deep">Deep</a>'),
                "/deep": Page(body=nested),
                "/after": Page(body="<p>After</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))
    ((parsed, parse_error),) = query(
        crawl_file, "SELECT parsed, parse_error FROM urls WHERE url = ?", [server.url("/deep")]
    )

    assert (crawl_row(crawl_file)["state"], parsed == 1 or parse_error is not None) == (
        "completed",
        True,
    )
