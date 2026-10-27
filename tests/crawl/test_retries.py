"""Timeouts and retries with backoff (022-add-fetch-policy, fetching; seam 3+6)."""

import pytest

from spider.naming import SETTINGS_FILE_NAME
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site, Status
from tests.support.cli import run_cli
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


def test_a_hanging_response_times_out(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A report page whose backend query never returns.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/hang">Report</a>'),
                "/hang": Page(body="<title>Report</title>", hang=True),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--timeout", "1", "--retries", "0")

    assert query(
        crawl_file,
        "SELECT fetch_state, status_code, fetch_error FROM urls WHERE url = ?",
        [server.url("/hang")],
    ) == [("error", None, "timeout")]


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_a_timeout_that_is_not_a_finite_number_above_0_is_rejected(
    temp_workspace: TempWorkspace, timeout: str
) -> None:
    result = run_cli("crawl", "http://site.test/", "--timeout", timeout)

    assert (
        result.exit_code,
        [(error["code"], "--timeout" in error["message"]) for error in result.errors()],
    ) == (2, [("invalid_value", True)])


@pytest.mark.parametrize("timeout", ["0", "-1.5", "nan", "inf"])
def test_a_timeout_in_the_settings_file_that_is_not_a_finite_number_above_0_is_refused(
    temp_workspace: TempWorkspace, timeout: str
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(
        f"[crawl]\ntimeout = {timeout}\n".encode()
    )

    result = run_cli("crawl", "http://site.test/")

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
    ) == (3, [("settings_invalid", "crawl.timeout")])


def test_a_whole_number_timeout_in_the_settings_file_is_taken(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Shop</title>")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(b"[crawl]\ntimeout = 5\n")

    result = run_cli("crawl", server.url("/"))

    assert (result.exit_code, result.errors()) == (0, [])
