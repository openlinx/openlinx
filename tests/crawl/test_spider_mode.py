"""Spider mode over HTTP (020-add-crawl-core, crawling; seam 3+6)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.sites.hostile import site as hostile
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row, query
from tests.support.network import closed_port
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


def test_undecodable_bytes_do_not_stop_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(hostile.SITE)

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", [server.url("/after")]
    ) == [("fetched",)]


def test_a_closed_port_is_a_refused_connection(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    target = f"http://127.0.0.1:{closed_port()}/"
    server = fixture_site(Site(routes={"/": Page(body=f'<a href="{target}">Gone</a>')}))

    crawl_file = crawled(server.url("/"))
    ((fetch_state, status_code, fetch_error, message),) = query(
        crawl_file,
        "SELECT fetch_state, status_code, fetch_error, fetch_error_message FROM urls WHERE url = ?",
        [target],
    )

    assert (fetch_state, status_code, fetch_error, bool(message)) == (
        "error",
        None,
        "connection_refused",
        True,
    )


def test_a_connection_reset_in_the_body_is_a_connection_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/reset">Reset</a> <a href="/after">After</a>'),
                "/reset": Page(body="<p>" + "x" * 100_000 + "</p>", reset_after=100),
                "/after": Page(body="<p>After</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert sorted(
        query(
            crawl_file,
            "SELECT url, fetch_state, fetch_error FROM urls WHERE url IN (?, ?)",
            [server.url("/reset"), server.url("/after")],
        )
    ) == [
        (server.url("/after"), "fetched", None),
        (server.url("/reset"), "error", "connection_error"),
    ]


SLOW_PAGES = Site(
    routes={
        "/": Page(body=" ".join(f'<a href="/slow/{n}">{n}</a>' for n in range(1, 21))),
        **{f"/slow/{n}": Page(body="<p>Slow</p>", delay=0.5) for n in range(1, 21)},
    }
)


@pytest.mark.slow
def test_at_most_five_requests_to_a_host_by_default(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_PAGES)

    crawled(server.url("/"))

    assert server.most_simultaneous == 5


@pytest.mark.slow
def test_a_lower_concurrency_is_honoured(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_PAGES)

    crawled(server.url("/"), "--concurrency", "2")

    assert server.most_simultaneous == 2


def test_urls_that_differ_only_in_stripped_parameters_are_fetched_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/p?utm_source=a">A</a><a href="/p?utm_source=b">B</a>'),
                "/p": Page(body="<p>P</p>"),
            }
        )
    )

    crawled(server.url("/"), "--strip-params", "utm_*")

    assert [request.path for request in server.requests if request.path != "/"] == ["/p"]


def test_the_seed_is_stripped_of_its_parameters_too(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))

    crawl_file = crawled(server.url("/?utm_source=mail&id=7"), "--strip-params", "utm_*")

    assert (
        query(crawl_file, "SELECT url FROM urls"),
        [request.path for request in server.requests],
    ) == ([(server.url("/?id=7"),)], ["/?id=7"])
