"""Timeouts and retries with backoff (022-add-fetch-policy, fetching; seam 3+6)."""

import pytest

from spider.naming import SETTINGS_FILE_NAME
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


@pytest.mark.slow
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


@pytest.mark.slow
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


# A report page whose backend query never returns.
HANGING_REPORT = Site(
    {
        "/": Page(body='<title>Shop</title><a href="/hang">Report</a>'),
        "/hang": Page(body="<title>Report</title>", hang=True),
    }
)


@pytest.mark.slow
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


@pytest.mark.slow
def test_a_trickling_body_times_out(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # A hostile or broken server: the headers, then one byte at a time, never ending.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/feed">Feed</a>'),
                "/feed": Page(body="never", trickle=True),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--timeout", "1", "--retries", "0")

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error FROM urls WHERE url = ?",
        [server.url("/feed")],
    ) == [("error", "timeout")]


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


@pytest.mark.slow
def test_a_whole_number_timeout_in_the_settings_file_is_taken(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HANGING_REPORT)
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(b"[crawl]\ntimeout = 1\nretries = 0\n")

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT fetch_error FROM urls WHERE url = ?", [server.url("/hang")]
    ) == [("timeout",)]


@pytest.mark.slow
def test_a_request_without_a_response_is_retried(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HANGING_REPORT)

    crawl_file = crawled(server.url("/"), "--timeout", "1", "--retries", "1")

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error, attempt_count FROM urls WHERE url = ?",
        [server.url("/hang")],
    ) == [("error", "timeout", 2)]


@pytest.mark.slow
def test_robots_txt_is_retried(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # The host restarts while the Crawl asks for robots.txt: one 503, then the rules.
    rules = Robots("User-agent: *\nDisallow: /private\n")
    server = fixture_site(
        Site(
            {
                "/robots.txt": Responses((Status(503), rules)),
                "/": Page(body='<title>Shop</title><a href="/private">Account</a>'),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, skip_reason, attempt_count FROM urls WHERE url = ?",
        [server.url("/private")],
    ) == [("skipped", "blocked_by_robots_txt", 0)]


@pytest.mark.slow
def test_a_robots_txt_that_times_out_gives_its_urls_timeout_without_a_request(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nAllow: /\n", hang=True),
                "/": Page(body="<title>Shop</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--timeout", "1", "--retries", "0")

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, fetch_error, fetched_at, attempt_count FROM urls WHERE url = ?",
            [server.url("/")],
        ),
        [request.path for request in server.requests],
    ) == ([("error", "timeout", None, 0)], ["/robots.txt"])


@pytest.mark.slow
def test_only_the_first_attempt_counts_towards_the_url_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/flaky">Sale</a>'),
                "/flaky": Responses((Status(503), Page(body="<title>Sale</title>"))),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-urls", "2")

    assert query(
        crawl_file,
        "SELECT status_code, attempt_count FROM urls WHERE url = ?",
        [server.url("/flaky")],
    ) == [(200, 2)]


def test_an_unresolvable_external_host_is_requested_once(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    # A blog post that links to a shop whose domain has lapsed.
    hosts = fixture_hosts(
        Site({"/": Page(body='<title>Blog</title><a href="http://gone.test/">Old shop</a>')}),
        Site({}),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(crawl_file, "SELECT fetch_error FROM urls WHERE url = 'http://gone.test/'"),
        hosts.resolver.lookups.count("gone.test"),
    ) == ([("dns_error",)], 1)


def test_more_than_10_retries_are_rejected(temp_workspace: TempWorkspace) -> None:
    result = run_cli("crawl", "http://site.test/", "--retries", "11")

    assert (
        result.exit_code,
        [(error["code"], "--retries" in error["message"]) for error in result.errors()],
    ) == (2, [("invalid_value", True)])


def test_more_than_10_retries_in_the_settings_file_are_refused(
    temp_workspace: TempWorkspace,
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(b"[crawl]\nretries = 11\n")

    result = run_cli("crawl", "http://site.test/")

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
    ) == (3, [("settings_invalid", "crawl.retries")])
