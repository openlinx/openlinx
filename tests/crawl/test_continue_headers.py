"""Restore only recorded sensitive header occurrences before continuing a Crawl."""

import json
from contextlib import nullcontext
from functools import partial

import pytest

from openlinx.clock import SystemClock
from openlinx.crawl.engine.hooks import Hooks, UrlResult, handler
from openlinx.crawl.fetch.fetcher import aiohttp_fetcher
from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides, CrawlRequest, plan_crawl, start_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.page_records import PageRow
from openlinx.store.pages import write_pages
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import crawl_row, sha256_of
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("custom_user_agent", [False, True], ids=["dedicated-ua", "custom-ua"])
@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
def test_continue_refuses_a_missing_sensitive_header_value(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    custom_user_agent: bool,
    read_only: bool,
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(
        server.url("/"),
        header=["User-Agent: Header/1", "X-Env: staging", "Cookie: sid=old123"],
        user_agent=None if custom_user_agent else "Dedicated/1",
        max_urls=1,
        retries=0,
    )
    assert stopped.summary.state == "stopped"
    config = json.loads(crawl_row(stopped.crawl_file)["config"])
    assert config["crawl"]["header"] == ["User-Agent: Header/1", "X-Env: staging", "Cookie: ***"]
    before = sha256_of(stopped.crawl_file)
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    requests = server.requests
    reporter = Collected()

    with (
        read_only_file(stopped.crawl_file) if read_only else nullcontext(),
        pytest.raises(OpenLinxError) as caught,
    ):
        continued(stopped, CrawlOverrides(max_urls=None), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)
    assert caught.value.diagnostic.hint is not None
    assert "--header" in caught.value.diagnostic.hint
    assert all(
        value not in json.dumps(caught.value.diagnostic.to_json())
        for value in ("sid=old123", "***")
    )
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files
    assert server.requests == requests


@pytest.mark.parametrize(
    "fresh",
    [
        ("X-Env: changed",),
        ("X-Env: staging",),
        ("User-Agent: Changed/1",),
        ("Accept-Encoding: identity",),
        ("X-Unknown-Token: unknown123",),
        ("X-Token: new123", "x-token: extra123"),
        ("X-Token: new123", "Cookie: sid=new123", "Cookie: extra123"),
        ("NoColon",),
        (": no-name",),
        ("X Token: bad-name",),
        ("X-Token: bad\r\nHost: injected",),
        ("X-Token: £",),
        ("X-Token: \ud800",),
        ("X-Token: ***",),
        ("Cookie:\t*** \t",),
        ("X-Token: ***", "Cookie: sid=new123"),
        ("X-Token: new123", "Cookie: \t*** \t"),
    ],
)
def test_invalid_fresh_headers_are_refused_before_missing_values_or_writer_access(
    temp_workspace: TempWorkspace, fixture_site: StartSite, fresh: tuple[str, ...]
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(
        server.url("/"),
        header=["X-Env: staging", "X-Token: old123", "Cookie: sid=old123"],
        max_urls=1,
        retries=0,
    )
    assert json.loads(crawl_row(stopped.crawl_file)["config"])["crawl"]["header"] == [
        "X-Env: staging",
        "X-Token: ***",
        "Cookie: ***",
    ]
    before = sha256_of(stopped.crawl_file)
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    requests = server.requests
    reporter = Collected()

    with read_only_file(stopped.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(stopped, CrawlOverrides(header=fresh), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "invalid_value",
        2,
        {"key": "crawl.header"},
    )
    diagnostic = json.dumps(caught.value.diagnostic.to_json())
    assert all(json.dumps(value)[1:-1] not in diagnostic for value in fresh)
    assert "***" not in diagnostic
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files
    assert server.requests == requests


@pytest.mark.parametrize(
    "fresh",
    [(), ("X-Token: new123",), ("X-Token: new123", "Cookie: sid=new123")],
)
def test_each_recorded_sensitive_header_occurrence_needs_a_fresh_value(
    temp_workspace: TempWorkspace, fixture_site: StartSite, fresh: tuple[str, ...]
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(
        server.url("/"),
        header=["X-Token: old123", "x-token: old456", "Cookie: sid=old123"],
        max_urls=1,
        retries=0,
    )
    before = sha256_of(stopped.crawl_file)
    requests = server.requests
    reporter = Collected()

    with read_only_file(stopped.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(stopped, CrawlOverrides(header=fresh), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)
    assert caught.value.diagnostic.hint is not None
    assert "--header" in caught.value.diagnostic.hint
    assert "***" not in json.dumps(caught.value.diagnostic.to_json())
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert server.requests == requests


def test_fresh_credentials_preserve_stored_harmless_settings(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="/last">Last</a>'),
            }
        )
    )
    stopped = crawl_result(
        server.url("/"),
        header=["X-Env:\tstaging ", "x-ToKeN: old123", "X-Env: audit"],
        timeout=7,
        max_urls=1,
        retries=0,
    )
    original = json.loads(crawl_row(stopped.crawl_file)["config"])
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        '[crawl]\ntimeout = 99\nheader = ["X-Token: workspace"]\nauth = "workspace:changed"\n'
    )
    requests_before = len(server.requests)

    result = continued(stopped, CrawlOverrides(max_urls=2, header=("X-TOKEN: new123",)))

    assert result.summary.state == "stopped"
    assert [
        (
            r.path,
            r.headers.getall("X-Env"),
            r.headers.getall("X-Token"),
            r.headers.getall("Authorization", []),
        )
        for r in server.requests[requests_before:]
    ] == [
        ("/robots.txt", ["staging", "audit"], ["new123"], []),
        ("/next", ["staging", "audit"], ["new123"], []),
    ]
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["crawl"] == {**original["crawl"], "max_urls": 2}
    assert config["crawl"]["header"] == ["X-Env:\tstaging ", "x-ToKeN: ***", "X-Env: audit"]
    assert config["request_policy"] == original["request_policy"]
    assert b"new123" not in result.crawl_file.read_bytes()
    with pytest.raises(OpenLinxError) as caught:
        continued(result, CrawlOverrides(max_urls=None))
    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)


def test_sensitive_header_occurrences_keep_recorded_names_and_positions(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    headers = [
        "X-Env:\tstaging ",
        "x-ToKeN: old1",
        "Cookie: a=old",
        "X-TOKEN: old2",
        "X-Env:audit",
        "cookie: b=old",
        "X-Api-Key: oldkey",
        "X-Secret: oldsecret",
        "X-Password: oldpass",
        "AUTH-Thing: oldauth",
    ]
    stopped = crawl_result(server.url("/"), header=headers, max_urls=1, retries=0)
    requests_before = len(server.requests)

    result = continued(
        stopped,
        CrawlOverrides(
            max_urls=None,
            header=(
                "cookie: a=new123",
                "X-API-KEY: key123",
                "x-token: tokenFirst123",
                "X-PASSWORD: pass123",
                "Cookie: b=new456",
                "auth-thing: auth123",
                "X-SECRET: secret123",
                "X-TOKEN: tokenSecond456",
            ),
        ),
    )

    assert result.summary.state == "completed"
    assert [
        (
            r.headers.getall("X-Env"),
            r.headers.getall("X-Token"),
            r.headers.getall("Cookie"),
            r.headers["X-Api-Key"],
            r.headers["X-Secret"],
            r.headers["X-Password"],
            r.headers["AUTH-Thing"],
        )
        for r in server.requests[requests_before:]
    ] == [
        (
            ["staging", "audit"],
            ["tokenFirst123", "tokenSecond456"],
            ["a=new123", "b=new456"],
            "key123",
            "secret123",
            "pass123",
            "auth123",
        ),
    ] * 2
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["header"] == [
        "X-Env:\tstaging ",
        "x-ToKeN: ***",
        "Cookie: ***",
        "X-TOKEN: ***",
        "X-Env:audit",
        "cookie: ***",
        "X-Api-Key: ***",
        "X-Secret: ***",
        "X-Password: ***",
        "AUTH-Thing: ***",
    ]


@pytest.mark.parametrize("value", ["", " \t "])
def test_an_explicit_empty_sensitive_header_value_is_fresh_input(
    temp_workspace: TempWorkspace, fixture_site: StartSite, value: str
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(server.url("/"), header=["X-Token: old123"], max_urls=1, retries=0)
    requests_before = len(server.requests)

    result = continued(stopped, CrawlOverrides(max_urls=None, header=(f"X-Token:{value}",)))

    assert result.summary.state == "completed"
    assert [
        (r.headers.getall("X-Token"), r.headers.getall("Authorization", []))
        for r in server.requests[requests_before:]
    ] == [([""], [])] * 2
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["header"] == ["X-Token: ***"]


def test_continue_preserves_a_cli_header_over_a_workspace_dedicated_user_agent(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    _assert_continued_user_agent_winner(
        temp_workspace,
        fixture_hosts,
        dedicated=False,
        expected_internal="Header/1",
        expected_custom=True,
    )


def test_continue_preserves_a_dedicated_winner_with_the_same_resolved_values(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    _assert_continued_user_agent_winner(
        temp_workspace,
        fixture_hosts,
        dedicated=True,
        expected_internal="File/1",
        expected_custom=False,
    )


def _assert_continued_user_agent_winner(
    workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    *,
    dedicated: bool,
    expected_internal: str,
    expected_custom: bool,
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="/last">Last</a>'),
                "/last": Page(body='<a href="http://other.test/page">Other</a>'),
            }
        ),
        Site({"/page": Page(body="Other")}),
    )
    (workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "File/1"\n')
    headers = ["User-Agent: Header/1", "X-Env: staging", "X-Token: old123", "X-Env: audit"]
    plan = plan_crawl(
        CrawlRequest(
            seed="http://site.test/",
            cwd=workspace.root,
            home=workspace.home,
            workspace=None,
            command_argv=["service-crawl"],
            secret_flags={},
            flags={
                "crawl": {
                    "header": headers,
                    "max_urls": 1,
                    "retries": 0,
                    **({"user_agent": "File/1"} if dedicated else {}),
                }
            },
        )
    )
    stopped = start_crawl(
        plan,
        SystemClock(),
        Collected(),
        default_hooks(),
        fetchers=partial(aiohttp_fetcher, resolver=hosts.resolver),
    )
    assert stopped.summary.state == "stopped"
    (workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nuser_agent = "Changed/1"\n')
    requests_before = len(hosts.site.requests)

    second = continued(
        stopped, CrawlOverrides(max_urls=2, header=("X-Token: new123",)), resolver=hosts.resolver
    )
    third = continued(
        second, CrawlOverrides(max_urls=None, header=("x-TOKEN: new456",)), resolver=hosts.resolver
    )

    assert (second.summary.state, third.summary.state) == ("stopped", "completed")
    assert [
        (r.headers.getall("User-Agent"), r.headers.getall("X-Env"), r.headers.getall("X-Token"))
        for r in hosts.site.requests[requests_before:]
    ] == [
        ([expected_internal], ["staging", "audit"], [value])
        for value in ["new123", "new123", "new456", "new456"]
    ]
    assert [
        (
            r.headers.getall("User-Agent"),
            r.headers.getall("X-Token", []),
            r.headers.getall("X-Env", []),
        )
        for r in hosts.other.requests
    ] == [(["File/1"], [], [])] * 2
    for result in (second, third):
        config = json.loads(crawl_row(result.crawl_file)["config"])
        assert config["request_policy"] == {"custom_user_agent": expected_custom}
        assert config["crawl"]["user_agent"] == "File/1"
        assert config["crawl"]["header"] == [
            "User-Agent: Header/1",
            "X-Env: staging",
            "X-Token: ***",
            "X-Env: audit",
        ]


@pytest.mark.parametrize(
    ("headers", "internal"),
    [
        (["Accept-Encoding: identity"], ["identity"]),
        (["accept-encoding:"], [""]),
        (["Accept-Encoding: gzip;q=0", "aCcEpT-eNcOdInG: br"], ["gzip;q=0", "br"]),
    ],
)
def test_continue_preserves_an_internal_accept_encoding_override(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    headers: list[str],
    internal: list[str],
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="http://other.test/page">Other</a>'),
            }
        ),
        Site({"/page": Page(body="Other")}),
    )
    stopped = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        header=[*headers, "X-Token: old123"],
        max_urls=1,
        retries=0,
    )
    requests_before = len(hosts.site.requests)

    result = continued(
        stopped, CrawlOverrides(max_urls=None, header=("X-Token: new123",)), resolver=hosts.resolver
    )

    assert result.summary.state == "completed"
    assert [r.headers.getall("Accept-Encoding") for r in hosts.site.requests[requests_before:]] == [
        internal
    ] * 2
    assert [r.headers.getall("Accept-Encoding") for r in hosts.other.requests] == [
        ["gzip, deflate, br, zstd"]
    ] * 2
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["header"] == [
        *headers,
        "X-Token: ***",
    ]


@pytest.mark.parametrize("authorization", ["Authorization", "aUtHoRiZaTiOn"])
def test_restored_authorization_conflicts_with_fresh_auth_before_writer_access(
    temp_workspace: TempWorkspace, fixture_site: StartSite, authorization: str
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(
        server.url("/"), header=[f"{authorization}: Bearer old123"], max_urls=1, retries=0
    )
    assert json.loads(crawl_row(stopped.crawl_file)["config"])["crawl"]["auth"] is None
    before = sha256_of(stopped.crawl_file)
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    requests = server.requests
    reporter = Collected()

    with read_only_file(stopped.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(
            stopped,
            CrawlOverrides(auth="alice:newpass", header=("AUTHORIZATION: Bearer new123",)),
            reporter=reporter,
        )

    assert (caught.value.code, caught.value.exit_code) == ("invalid_value", 2)
    diagnostic = json.dumps(caught.value.diagnostic.to_json())
    assert all(value not in diagnostic for value in ("alice:newpass", "newpass", "new123", "***"))
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files
    assert server.requests == requests


@pytest.mark.parametrize("auth", [None, ""], ids=["null", "empty"])
def test_disabled_auth_allows_a_restored_authorization_header(
    temp_workspace: TempWorkspace, fixture_site: StartSite, auth: str | None
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(
        server.url("/"), header=["Authorization: Bearer old123"], max_urls=1, retries=0
    )
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text('[crawl]\nauth = "workspace:changed"\n')
    requests_before = len(server.requests)

    result = continued(
        stopped, CrawlOverrides(max_urls=None, auth=auth, header=("authorization: Bearer new123",))
    )

    assert result.summary.state == "completed"
    assert [r.headers.getall("Authorization") for r in server.requests[requests_before:]] == [
        ["Bearer new123"]
    ] * 2
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["crawl"]["auth"] is None
    assert config["crawl"]["header"] == ["Authorization: ***"]


def _refuse_fresh_credentials(result: UrlResult) -> tuple[PageRow, ...]:
    raise ValueError(
        "refused tokenNew123 / sid=new123 / test:123£ / 123£ / "
        "dGVzdDoxMjPCow== / Basic dGVzdDoxMjPCow==; staging"
    )


def test_fresh_header_and_auth_values_are_masked_in_continue_diagnostics(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(
        server.url("/"),
        auth="alice:oldpass",
        header=["X-Token: old123", "Cookie: sid=old123"],
        max_urls=1,
        retries=0,
    )
    reporter = Collected()
    hooks = Hooks(handlers=(handler("fresh", _refuse_fresh_credentials, write_pages),))
    requests_before = len(server.requests)

    result = continued(
        stopped,
        CrawlOverrides(
            max_urls=None, auth="test:123£", header=("x-token: tokenNew123", "COOKIE: sid=new123")
        ),
        hooks,
        reporter=reporter,
    )

    assert result.summary.state == "completed"
    assert [
        (r.headers.getall("Authorization"), r.headers.getall("X-Token"), r.headers.getall("Cookie"))
        for r in server.requests[requests_before:]
    ] == [(["Basic dGVzdDoxMjPCow=="], ["tokenNew123"], ["sid=new123"])] * 2
    for diagnostics in (
        [warning.to_json() for warning in reporter.warnings],
        [warning.to_json() for warning in result.warnings],
        json.loads(crawl_row(result.crawl_file)["warnings"]),
    ):
        assert [(item["code"], item["details"]["error"]) for item in diagnostics] == [
            ("handler_failed", "refused *** / *** / *** / *** / *** / ***; staging")
        ]
        text = json.dumps(diagnostics, ensure_ascii=False)
        assert all(
            value not in text
            for value in (
                "tokenNew123",
                "sid=new123",
                "test:123£",
                "123£",
                "dGVzdDoxMjPCow==",
                "Basic dGVzdDoxMjPCow==",
            )
        )
