"""Verify Basic Auth inputs on the wire and in recorded Crawl metadata."""

import json
import socket
from pathlib import Path

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
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
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise OSError(
            None,
            "refused test:123£ / 123£ / dGVzdDoxMjPCow== / Basic dGVzdDoxMjPCow==; staging",
        )

    async def close(self) -> None:
        pass


def test_transport_failures_hide_exact_utf8_credentials_and_their_wire_forms(
    temp_workspace: TempWorkspace,
) -> None:
    result = crawl_result(
        "http://site.test/",
        auth="test:123£",
        resolver=QuotingAuthResolver(),
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
