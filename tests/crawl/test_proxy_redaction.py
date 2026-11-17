"""Verify what the Crawl records and reports about proxy credentials."""

import json
import socket

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.crawl.engine.hooks import Hooks, UrlResult, handler
from openlinx.output.reporter import Collected
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace


class QuotingProxyResolver(AbstractResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise OSError(None, "proxy refused 'relay%40pass' (decoded 'relay@pass')")

    async def close(self) -> None:
        pass


def test_a_quoted_proxy_password_is_hidden_in_request_failures(
    temp_workspace: TempWorkspace,
) -> None:
    result = crawl_result(
        "http://site.test/",
        proxy="http://u:relay%40pass@proxy.test:3128",
        resolver=QuotingProxyResolver(),
        retries=0,
        network_wait=0,
    )

    [(url_error, url_message)] = query(
        result.crawl_file, "SELECT fetch_error, fetch_error_message FROM urls"
    )
    [(robots_error, robots_message)] = query(
        result.crawl_file, "SELECT robots_fetch_error, robots_fetch_error_message FROM origins"
    )
    assert (url_error, robots_error) == ("dns_error", "dns_error")
    for message in (url_message, robots_message):
        assert "proxy refused '***' (decoded '***')" in message
        assert "relay%40pass" not in message
        assert "relay@pass" not in message


def _quote_proxy_password(_result: UrlResult) -> tuple[str, ...]:
    raise ValueError("proxy authentication refused 'relay@pass'")


def test_a_quoted_proxy_password_is_hidden_in_emitted_and_recorded_warnings(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
) -> None:
    hosts = fixture_hosts(Site({"/": Page(body="<title>Shop</title>")}), Site({}))
    proxy = fixture_proxy(hosts.resolver)
    hooks = Hooks(
        handlers=(handler("quote_proxy", _quote_proxy_password, lambda _db, _rows: None),)
    )
    reporter = Collected()

    result = crawl_result(
        "http://site.test/",
        hooks,
        proxy=proxy.url.replace("http://", "http://u:relay%40pass@"),
        reporter=reporter,
    )

    [(stored,)] = query(result.crawl_file, "SELECT warnings FROM crawl")
    assert (
        result.summary.state,
        [(warning.code, warning.details["error"]) for warning in reporter.warnings],
        [(warning["code"], warning["details"]["error"]) for warning in json.loads(stored)],
    ) == (
        "completed",
        [("handler_failed", "proxy authentication refused '***'")],
        [("handler_failed", "proxy authentication refused '***'")],
    )


@pytest.mark.parametrize("source", ["split", "joined", "workspace"])
@pytest.mark.parametrize(
    ("userinfo", "recorded_userinfo"),
    [("relay:p%40ss%3Aword@", "relay:***@"), ("", "")],
    ids=["password", "credential-free"],
)
def test_a_proxy_password_is_redacted(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    userinfo: str,
    recorded_userinfo: str,
) -> None:
    hosts = fixture_hosts(Site({"/": Page(body="<title>Shop</title>")}), Site({}))
    proxy = fixture_proxy(hosts.resolver)
    address = proxy.url.removeprefix("http://")
    explicit = f"http://{userinfo}{address}"
    recorded = f"http://{recorded_userinfo}{address}"
    monkeypatch.setenv("HTTP_PROXY", "http://worker:env-pass@proxy.test:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.test:3128")
    monkeypatch.setenv("NO_PROXY", "other.test")
    flags: tuple[str, ...] = ()
    recorded_flags: tuple[str, ...] = ()
    if source == "split":
        flags = ("--proxy", explicit)
        recorded_flags = ("--proxy", recorded)
    elif source == "joined":
        flags = (f"--proxy={explicit}",)
        recorded_flags = (f"--proxy={recorded}",)
    else:
        (temp_workspace.root / "openlinx.toml").write_text(
            f'[crawl]\nproxy = "{explicit}"\n', encoding="utf-8"
        )

    file = crawled("http://site.test/", *flags)
    [(argv, config)] = query(file, "SELECT command_argv, config FROM crawl")
    settings = json.loads(config)

    assert (json.loads(argv), settings["crawl"]["proxy"], settings["environment"]) == (
        ["linx", "crawl", "http://site.test/", *recorded_flags],
        recorded,
        {
            "http_proxy": "http://worker:***@proxy.test:3128",
            "https_proxy": "***",
            "no_proxy": "other.test",
        },
    )
