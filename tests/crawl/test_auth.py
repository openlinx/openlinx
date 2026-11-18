"""Verify Basic Auth inputs on the wire and in recorded Crawl metadata."""

import json
import socket
from pathlib import Path

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


def test_credentials_are_sent_to_internal_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    _assert_internal_auth(fixture_site, "alice:s3cret", "Basic YWxpY2U6czNjcmV0")


@pytest.mark.parametrize(
    ("auth", "authorization"),
    [
        ("test:123£", "Basic dGVzdDoxMjPCow=="),
        ("алиса:пароль", "Basic 0LDQu9C40YHQsDrQv9Cw0YDQvtC70Yw="),
        ("test:pa\u0308ss", "Basic dGVzdDpwYcyIc3M="),
        ("alice:", "Basic YWxpY2U6"),
        (":s3cret", "Basic OnMzY3JldA=="),
        (":", "Basic Og=="),
        (" alice :s3cret: ", "Basic IGFsaWNlIDpzM2NyZXQ6IA=="),
        ("https://alice:s3cret@site.test", "Basic aHR0cHM6Ly9hbGljZTpzM2NyZXRAc2l0ZS50ZXN0"),
    ],
    ids=[
        "pound",
        "cyrillic",
        "decomposed",
        "empty-password",
        "empty-user",
        "empty-parts",
        "whitespace-and-colon",
        "url-shaped",
    ],
)
def test_non_ascii_credentials_use_exact_utf_8_bytes(
    temp_workspace: TempWorkspace, fixture_site: StartSite, auth: str, authorization: str
) -> None:
    _assert_internal_auth(fixture_site, auth, authorization)


def _assert_internal_auth(fixture_site: StartSite, auth: str, authorization: str) -> None:
    server = fixture_site(Site({"/": Page(body="<title>Home</title>")}))

    result = run_cli("crawl", server.url("/"), "--auth", auth)

    assert result.exit_code == 0, result.stderr
    request = next(request for request in server.requests if request.path == "/")
    assert request.headers.getall("Authorization", []) == [authorization]
    file = Path(result.json()["crawl_file"])
    assert query(
        file, "SELECT status_code, is_internal FROM urls WHERE url = ?", [server.url("/")]
    ) == [(200, 1)]
    row = crawl_row(file)
    assert json.loads(row["config"])["crawl"]["auth"] == "***"
    assert json.loads(row["command_argv"])[-2:] == ["--auth", "***"]


@pytest.mark.parametrize("joined", [False, True], ids=["split", "joined"])
@pytest.mark.parametrize(
    ("auth", "authorization"),
    [
        ("alice:s3cret", "Basic YWxpY2U6czNjcmV0"),
        ("https://alice:s3cret@site.test", "Basic aHR0cHM6Ly9hbGljZTpzM2NyZXRAc2l0ZS50ZXN0"),
        ("--header=X-Env: credential", "Basic LS1oZWFkZXI9WC1FbnY6IGNyZWRlbnRpYWw="),
    ],
    ids=["plain", "url-shaped", "flag-shaped"],
)
def test_the_recorded_command_hides_the_password(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    auth: str,
    authorization: str,
    joined: bool,
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    flags = [f"--auth={auth}"] if joined else ["--auth", auth]

    result = run_cli(
        "crawl",
        server.url("/"),
        "--header",
        "X-Env: staging",
        *flags,
        "--header=x-env: audit",
        "--retries=0",
    )

    assert result.exit_code == 0, result.stderr
    assert [
        (request.path, request.headers.getall("Authorization", [])) for request in server.requests
    ] == [("/robots.txt", [authorization]), ("/", [authorization])]
    file = Path(result.json()["crawl_file"])
    row = crawl_row(file)
    assert json.loads(row["command_argv"]) == (
        [
            "linx",
            "crawl",
            server.url("/"),
            "--header",
            "X-Env: staging",
            "--auth=***",
            "--header=x-env: audit",
            "--retries=0",
        ]
        if joined
        else [
            "linx",
            "crawl",
            server.url("/"),
            "--header",
            "X-Env: staging",
            "--auth",
            "***",
            "--header=x-env: audit",
            "--retries=0",
        ]
    )
    config = json.loads(row["config"])["crawl"]
    assert config["auth"] == "***"
    assert config["header"] == ["X-Env: staging", "x-env: audit"]
    assert config["retries"] == 0
    assert query(file, "SELECT fetch_state, status_code FROM urls") == [("fetched", 200)]
    assert [(request.path, request.headers.getall("X-Env", [])) for request in server.requests] == [
        ("/robots.txt", ["staging", "audit"]),
        ("/", ["staging", "audit"]),
    ]


def test_internal_robots_requests_carry_credentials(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site({"/robots.txt": Robots("User-agent: *\nDisallow:\n"), "/": Page(body="Home")}),
        Site({}),
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver, auth="alice:s3cret")

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
    assert query(
        result.crawl_file,
        "SELECT is_internal, fetch_state, status_code FROM urls WHERE url = ?",
        ["http://site.test/"],
    ) == [(1, "fetched", 200)]
    assert hosts.other.requests == ()


def test_credentials_in_openlinx_toml_are_used(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        '[crawl]\nauth = "alice:s3cret"\nheader = ["X-Env: staging", "x-env: audit"]\n',
        encoding="utf-8",
    )

    result = run_cli("crawl", server.url("/"), "--retries=0")

    assert result.exit_code == 0, result.stderr
    assert [
        (request.path, request.headers.getall("Authorization", [])) for request in server.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
    assert [(request.path, request.headers.getall("X-Env", [])) for request in server.requests] == [
        ("/robots.txt", ["staging", "audit"]),
        ("/", ["staging", "audit"]),
    ]
    file = Path(result.json()["crawl_file"])
    row = crawl_row(file)
    config = json.loads(row["config"])["crawl"]
    assert config["auth"] == "***"
    assert config["header"] == ["X-Env: staging", "x-env: audit"]
    assert json.loads(row["command_argv"]) == ["linx", "crawl", server.url("/"), "--retries=0"]
    assert query(file, "SELECT fetch_state, status_code FROM urls") == [("fetched", 200)]


def test_a_robots_redirect_drops_credentials_at_an_external_hop(
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

    result = crawl_result("http://site.test/", resolver=hosts.resolver, auth="alice:s3cret")

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in hosts.site.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in hosts.other.requests
    ] == [("/robots.txt", [])]
    assert query(
        result.crawl_file,
        "SELECT is_internal, fetch_state, status_code FROM urls WHERE url = ?",
        ["http://site.test/"],
    ) == [(1, "fetched", 200)]
    assert query(
        result.crawl_file,
        "SELECT origin, is_internal, robots_state, robots_status_code FROM origins",
    ) == [("http://site.test", 1, "ok", 200)]


@pytest.mark.parametrize("custom_authorization", [False, True], ids=["basic-auth", "custom-auth"])
def test_credentials_never_go_to_external_urls(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, custom_authorization: bool
) -> None:
    hosts = fixture_hosts(
        Site({"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site({"/page": Page(body="Other")}),
    )
    headers = ["X-Env: staging", "X-Token: abc123", "x-env: audit"]
    if custom_authorization:
        headers.append("aUtHoRiZaTiOn: Bearer token123")

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        auth=None if custom_authorization else "alice:s3cret",
        header=headers,
    )

    assert result.summary.state == "completed"
    assert [
        (
            request.path,
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
            request.headers.getall("X-Token", []),
        )
        for request in hosts.site.requests
        if request.path != "/robots.txt"
    ] == [
        (
            "/",
            ["Bearer token123"] if custom_authorization else ["Basic YWxpY2U6czNjcmV0"],
            ["staging", "audit"],
            ["abc123"],
        )
    ]
    assert [
        (
            request.path,
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
            request.headers.getall("X-Token", []),
        )
        for request in hosts.other.requests
        if request.path != "/robots.txt"
    ] == [("/page", [], [], [])]
    assert query(
        result.crawl_file,
        "SELECT url, is_internal, status_code, fetch_state FROM urls ORDER BY url",
    ) == [
        ("http://other.test/page", 0, 200, "fetched"),
        ("http://site.test/", 1, 200, "fetched"),
    ]


@pytest.mark.parametrize("redirect_source", ["seed", "ordinary"])
@pytest.mark.parametrize("custom_authorization", [False, True], ids=["basic-auth", "custom-auth"])
def test_an_external_url_redirect_never_inherits_credentials(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    redirect_source: str,
    custom_authorization: bool,
) -> None:
    site = (
        Site({"/": Redirect("http://other.test/page", status=302)})
        if redirect_source == "seed"
        else Site(
            {
                "/": Page(body='<a href="/jump">Jump</a>'),
                "/jump": Redirect("http://other.test/page", status=302),
            }
        )
    )
    hosts = fixture_hosts(site, Site({"/page": Page(body="Other")}))
    headers = ["X-Env: staging", "X-Token: abc123", "x-env: audit"]
    if custom_authorization:
        headers.append("aUtHoRiZaTiOn: Bearer token123")

    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        auth=None if custom_authorization else "alice:s3cret",
        header=headers,
    )

    assert result.summary.state == "completed"
    assert [
        (
            request.path,
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
            request.headers.getall("X-Token", []),
        )
        for request in hosts.site.requests
        if request.path != "/robots.txt"
    ] == [
        (
            path,
            ["Bearer token123"] if custom_authorization else ["Basic YWxpY2U6czNjcmV0"],
            ["staging", "audit"],
            ["abc123"],
        )
        for path in (["/"] if redirect_source == "seed" else ["/", "/jump"])
    ]
    assert [
        (
            request.path,
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
            request.headers.getall("X-Token", []),
        )
        for request in hosts.other.requests
        if request.path != "/robots.txt"
    ] == [("/page", [], [], [])]
    expected_urls = [
        ("http://other.test/page", 0, 200, "fetched"),
        ("http://site.test/", 1, 302 if redirect_source == "seed" else 200, "fetched"),
    ]
    if redirect_source == "ordinary":
        expected_urls.append(("http://site.test/jump", 1, 302, "fetched"))
    assert (
        query(
            result.crawl_file,
            "SELECT url, is_internal, status_code, fetch_state FROM urls ORDER BY url",
        )
        == expected_urls
    )
    assert query(
        result.crawl_file,
        "SELECT source.url, target.url FROM urls AS source "
        "JOIN urls AS target ON source.redirect_url_id = target.id",
    ) == [
        (
            "http://site.test/" if redirect_source == "seed" else "http://site.test/jump",
            "http://other.test/page",
        )
    ]


@pytest.mark.parametrize("auth_source", ["flags", "settings"])
def test_authentication_conflicts_across_settings_sources(
    temp_workspace: TempWorkspace, fixture_site: StartSite, auth_source: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    if auth_source == "flags":
        settings = '[crawl]\nheader = ["X-Env: staging", "aUtHoRiZaTiOn: Bearer abc123"]\n'
        flags = ["--auth", "alice:s3cret"]
    else:
        settings = '[crawl]\nauth = "alice:s3cret"\nheader = ["X-Env: staging"]\n'
        flags = ["--header", "aUtHoRiZaTiOn: Bearer abc123"]
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(settings, encoding="utf-8")

    result = run_cli("crawl", server.url("/"), *flags)

    assert (result.exit_code, [error["code"] for error in result.errors()]) == (
        2,
        ["invalid_value"],
    )
    assert server.requests == ()
    assert list(temp_workspace.home.rglob("*.sqlite")) == []


@pytest.mark.parametrize("source", ["flags", "settings", "service"])
def test_conflicting_authentication_is_refused_before_network(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    if source == "service":
        with pytest.raises(OpenLinxError) as caught:
            crawl_result(
                server.url("/"), auth="alice:s3cret", header=["aUtHoRiZaTiOn: Bearer abc123"]
            )
        assert (caught.value.code, caught.value.exit_code) == ("invalid_value", 2)
        diagnostic = str(caught.value)
    else:
        flags = ["--auth", "alice:s3cret", "--header", "aUtHoRiZaTiOn: Bearer abc123"]
        if source == "settings":
            (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
                '[crawl]\nauth = "alice:s3cret"\nheader = ["aUtHoRiZaTiOn: Bearer abc123"]\n',
                encoding="utf-8",
            )
            flags = []
        result = run_cli("crawl", server.url("/"), *flags)
        assert (result.exit_code, [error["code"] for error in result.errors()]) == (
            2,
            ["invalid_value"],
        )
        diagnostic = result.stderr.decode("utf-8")
    assert server.requests == ()
    assert list(temp_workspace.home.rglob("*.sqlite")) == []
    assert "s3cret" not in diagnostic
    assert "abc123" not in diagnostic


@pytest.mark.parametrize("source", ["flags", "settings", "service"])
@pytest.mark.parametrize(
    "auth",
    [
        "alice-s3cret",
        *[f"alice:s3cret{chr(n)}" for n in (*range(32), 127)],
        *[f"alice:s3cret{chr(n)}" for n in (0xD800, 0xDFFF)],
    ],
    ids=[
        "missing-colon",
        *[f"ctl-{n:02x}" for n in (*range(32), 127)],
        "high-surrogate",
        "low-surrogate",
    ],
)
def test_malformed_credentials_are_refused_before_network(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, auth: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    expected_code, expected_exit = (
        ("settings_invalid", 3) if source == "settings" else ("invalid_value", 2)
    )
    if source == "service":
        with pytest.raises(OpenLinxError) as caught:
            crawl_result(server.url("/"), auth=auth, retries=0, network_wait=0)
        assert (caught.value.code, caught.value.exit_code) == (expected_code, expected_exit)
        diagnostic = str(caught.value)
    else:
        flags = ["--auth", auth]
        if source == "settings":
            (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
                f"[crawl]\nauth = {json.dumps(auth)}\n", encoding="utf-8"
            )
            flags = []
        result = run_cli("crawl", server.url("/"), *flags, "--retries", "0", "--network-wait", "0")
        assert (result.exit_code, [error["code"] for error in result.errors()]) == (
            expected_exit,
            [expected_code],
        )
        diagnostic = result.stderr.decode("utf-8")
    assert "s3cret" not in diagnostic
    assert "alice" not in diagnostic
    assert server.requests == ()
    assert list(temp_workspace.home.rglob("*.sqlite")) == []


@pytest.mark.parametrize("source", ["flags", "settings", "service"])
@pytest.mark.parametrize("authorization", [None, "Bearer abc123"])
def test_empty_auth_disables_basic_auth(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, authorization: str | None
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    header = f'header = ["Authorization: {authorization}"]\n' if authorization else ""
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        '[crawl]\nauth = "alice:s3cret"\n' + header, encoding="utf-8"
    )
    if source == "service":
        file = crawl_result(server.url("/"), auth="").crawl_file
    else:
        flags = ["--auth="]
        if source == "settings":
            (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
                '[crawl]\nauth = ""\n' + header, encoding="utf-8"
            )
            flags = []
        result = run_cli("crawl", server.url("/"), *flags)
        assert result.exit_code == 0, result.stderr
        file = Path(result.json()["crawl_file"])
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]
    assert all(
        request.headers.getall("Authorization", [])
        == ([] if authorization is None else [authorization])
        for request in server.requests
    )
    row = crawl_row(file)
    assert json.loads(row["config"])["crawl"]["auth"] is None
    if source == "flags":
        assert json.loads(row["command_argv"])[-1] == "--auth=***"


class QuotingAuthResolver(AbstractResolver):
    def __init__(self, message: str) -> None:
        self._message = message

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise OSError(None, self._message)

    async def close(self) -> None:
        pass


@pytest.mark.parametrize(
    ("auth", "password", "payload", "authorization"),
    [
        ("alice:s3cret", "s3cret", "YWxpY2U6czNjcmV0", "Basic YWxpY2U6czNjcmV0"),
        ("test:123£", "123£", "dGVzdDoxMjPCow==", "Basic dGVzdDoxMjPCow=="),
        (
            "алиса:пароль",
            "пароль",
            "0LDQu9C40YHQsDrQv9Cw0YDQvtC70Yw=",
            "Basic 0LDQu9C40YHQsDrQv9Cw0YDQvtC70Yw=",
        ),
        ("test:pa\u0308ss", "pa\u0308ss", "dGVzdDpwYcyIc3M=", "Basic dGVzdDpwYcyIc3M="),
    ],
    ids=["ascii", "pound", "cyrillic", "decomposed"],
)
def test_transport_failures_hide_exact_utf8_credentials_and_their_wire_forms(
    temp_workspace: TempWorkspace,
    auth: str,
    password: str,
    payload: str,
    authorization: str,
) -> None:
    result = crawl_result(
        "http://site.test/",
        auth=auth,
        resolver=QuotingAuthResolver(
            f"refused {auth} / {password} / {payload} / {authorization}; staging"
        ),
        retries=0,
        network_wait=0,
    )

    messages = query(
        result.crawl_file,
        "SELECT fetch_error, fetch_error_message FROM urls "
        "UNION ALL SELECT robots_fetch_error, robots_fetch_error_message FROM origins",
    )
    assert len(messages) == 2
    for code, message in messages:
        assert code == "dns_error"
        assert "refused *** / *** / *** / ***; staging" in message
        for secret in (auth, password, payload, authorization):
            assert secret not in message
