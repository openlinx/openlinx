"""Exercise scoped request headers through the CLI, HTTP and recorded Crawl metadata."""

import json
from pathlib import Path

import pytest

from openlinx.clock import SystemClock
from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.reporter import Collected
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Responses, Robots, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("source", ["flags", "settings"])
def test_a_custom_header_is_sent_to_internal_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))
    flags = ["--header", "X-Env: staging", "--header=X-Token: abc123"]
    if source == "settings":
        (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
            '[crawl]\nheader = ["X-Env: staging", "X-Token: abc123"]\n'
        )
        flags = []

    result = run_cli("crawl", server.url("/"), *flags)

    assert result.exit_code == 0
    request = next(request for request in server.requests if request.path == "/")
    assert (request.headers.get("X-Env"), request.headers.get("X-Token")) == ("staging", "abc123")
    crawl_file = Path(result.json()["crawl_file"])
    row = crawl_row(crawl_file)
    assert json.loads(row["config"])["crawl"]["header"] == ["X-Env: staging", "X-Token: ***"]
    if source == "flags":
        assert json.loads(row["command_argv"])[-3:] == [
            "--header",
            "X-Env: staging",
            "--header=X-Token: ***",
        ]
    assert b"abc123" not in crawl_file.read_bytes()


def test_a_custom_header_never_goes_to_external_urls(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site({"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site({"/page": Page(body="Other")}),
    )

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        header=["X-Env: staging", "X-Token: abc123", "x-env: audit"],
    )

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
    ]
    assert sorted(
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.other.requests
    ) == [("/page", [], []), ("/robots.txt", [], [])]


def test_an_external_url_redirect_never_inherits_custom_headers(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site({"/": Redirect("http://other.test/page")}),
        Site({"/page": Page(body="Other")}),
    )

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        header=["X-Env: staging", "X-Token: abc123", "x-env: audit"],
    )

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
    ]
    assert sorted(
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.other.requests
    ) == [("/page", [], []), ("/robots.txt", [], [])]


def test_internal_robots_requests_carry_custom_headers(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nDisallow:\n"),
                "/": Page(body="Home"),
            }
        ),
        Site({}),
    )

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        header=["X-Env: staging", "X-Token: abc123", "x-env: audit"],
    )

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
    ]
    assert hosts.other.requests == ()


def test_a_robots_redirect_drops_internal_headers_at_an_external_hop(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/robots.txt": Redirect("http://other.test/robots.txt"),
                "/": Page(body="Home"),
            }
        ),
        Site({"/robots.txt": Robots("User-agent: *\nDisallow:\n")}),
    )

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        header=["X-Env: staging", "X-Token: abc123", "x-env: audit"],
    )

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
    ]
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.other.requests
    ] == [("/robots.txt", [], [])]


@pytest.mark.slow
def test_the_seed_outage_probe_keeps_custom_headers(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/robots.txt": Responses(
                    (Robots("", hang=True), Robots("User-agent: *\nDisallow:\n"))
                ),
                "/": Page(body="Home"),
            }
        ),
        Site({}),
    )
    reporter = Collected()

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        reporter=reporter,
        clock=SystemClock(),
        timeout=1,
        retries=0,
        network_wait=30,
        auth="alice:s3cret",
        header=["X-Env: staging", "X-Token: abc123", "x-env: audit"],
    )

    assert result.summary.state == "completed"
    assert [
        (name, data.get("reason"), data.get("outcome"))
        for name, data in reporter.events
        if name in ("crawl_paused", "crawl_resumed")
    ] == [("crawl_paused", "timeout", None), ("crawl_resumed", None, "outage")]
    # robots.txt blocks the ordinary Seed request, so the first / is the outage probe.
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
    assert [
        (request.path, request.headers.getall("X-Env", []), request.headers.getall("X-Token", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
        ("/robots.txt", ["staging", "audit"], ["abc123"]),
        ("/", ["staging", "audit"], ["abc123"]),
    ]
    assert query(result.crawl_file, "SELECT url, fetch_state, attempt_count FROM urls") == [
        ("http://site.test/", "fetched", 1)
    ]
    assert hosts.other.requests == ()


@pytest.mark.parametrize(
    "header",
    [
        "X-Token: abc123\r\nInjected: value",
        "X-Token: abc123\x00",
        "Bad Name: abc123",
        " Cookie: sid=abc123",
        "X-Token: abc123\n",
        "X-Env: Мой бот",
    ],
)
def test_unsafe_headers_are_rejected_without_disclosing_their_values(
    temp_workspace: TempWorkspace, fixture_site: StartSite, header: str
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))

    result = run_cli("crawl", server.url("/"), "--header", header)

    assert (result.exit_code, [error["code"] for error in result.errors()], server.requests) == (
        2,
        ["invalid_value"],
        (),
    )
    assert b"abc123" not in result.stderr


@pytest.mark.parametrize("header", [" Cookie: sid=abc123", "X-Token: abc123\r\nInjected: value"])
def test_unsafe_workspace_headers_are_rejected_without_disclosing_their_values(
    temp_workspace: TempWorkspace, fixture_site: StartSite, header: str
) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        f"[crawl]\nheader = {json.dumps([header])}\n"
    )

    result = run_cli("crawl", server.url("/"))

    assert (result.exit_code, [error["code"] for error in result.errors()], server.requests) == (
        3,
        ["settings_invalid"],
        (),
    )
    assert b"abc123" not in result.stderr
