"""Retries with backoff (022-add-fetch-policy, fetching; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site, Status
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_a_temporary_503_is_retried(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # A shop whose application server restarts: one 503, then the page.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/flaky">Sale</a>'),
                "/flaky": Responses((Status(503), Page(body="<title>Sale</title>"))),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT status_code, attempt_count FROM urls WHERE url = ?",
        [server.url("/flaky")],
    ) == [(200, 2)]


def test_a_persistent_500_is_recorded_after_the_retries(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/down">Stock</a>'),
                "/down": Status(500, body="<h1>Internal Server Error</h1>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, status_code, attempt_count FROM urls WHERE url = ?",
            [server.url("/down")],
        ),
        [request.path for request in server.requests].count("/down"),
    ) == ([("fetched", 500, 3)], 3)


def test_a_404_is_not_retried(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site({"/": Page(body='<title>Shop</title><a href="/missing">Old offer</a>')})
    )

    crawl_file = crawled(server.url("/"))

    assert (
        query(
            crawl_file,
            "SELECT status_code, attempt_count FROM urls WHERE url = ?",
            [server.url("/missing")],
        ),
        [request.path for request in server.requests].count("/missing"),
    ) == ([(404, 1)], 1)
