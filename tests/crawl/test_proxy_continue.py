"""Exercise proxy restoration and redaction through the Crawl Service."""

import json
import socket

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.permissions import read_only_file
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SHOP = Site(
    {
        "/": Page(body='<a href="/next">Next</a>'),
        "/next": Page(body='<a href="/last">Last</a>'),
        "/last": Page(body="<title>Last</title>"),
    }
)


def test_continue_uses_fresh_proxy_credentials_and_keeps_recorded_config(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_tls_hosts(SHOP, Site({}))
    old_proxy = fixture_proxy(hosts.resolver, auth=("u", "old126"))
    new_proxy = fixture_proxy(hosts.resolver, auth=("u", "new126"))
    stopped = crawl_result(
        "https://site.test/",
        proxy=old_proxy.url.replace("http://", "http://u:old126@"),
        trust_anchors=hosts.trust_anchors,
        header=["User-Agent: Header/1", "X-Env: staging"],
        timeout=7,
        max_urls=1,
        concurrency=1,
        retries=0,
        network_wait=0,
    )
    assert stopped.summary.state == "stopped"
    before = crawl_row(stopped.crawl_file)
    old_tunnels = old_proxy.connect_requests
    assert {entry.headers.get("Proxy-Authorization") for entry in old_tunnels} == {
        "Basic dTpvbGQxMjY="
    }
    origin_count = len(hosts.secure_site.requests)
    (temp_workspace.root / "openlinx.toml").write_text(
        '[crawl]\nproxy = "http://127.0.0.1:1"\ntimeout = 1\nheader = ["X-Env: audit"]\n',
        encoding="utf-8",
    )

    result = continued(
        stopped,
        CrawlOverrides(max_urls=2, proxy=new_proxy.url.replace("http://", "u:new126@")),
        trust_anchors=hosts.trust_anchors,
    )

    assert result.summary.state == "stopped"
    assert old_proxy.connect_requests == old_tunnels
    assert {
        (entry.method, entry.target, entry.headers.get("Proxy-Authorization"))
        for entry in new_proxy.connect_requests
    } == {("CONNECT", "site.test:443", "Basic dTpuZXcxMjY=")}
    assert [
        (
            request.path,
            request.headers.get("Proxy-Authorization"),
            request.headers.get("User-Agent"),
            request.headers.get("X-Env"),
        )
        for request in hosts.secure_site.requests[origin_count:]
    ] == [("/robots.txt", None, "Header/1", "staging"), ("/next", None, "Header/1", "staging")]
    recorded = crawl_row(result.crawl_file)
    expected_config = json.loads(before["config"])
    expected_config["crawl"].update(
        max_urls=2, proxy=new_proxy.url.replace("http://", "http://u:***@")
    )
    assert json.loads(recorded["config"]) == expected_config
    assert recorded["command_argv"] == before["command_argv"]
    file_bytes = result.crawl_file.read_bytes()
    assert all(secret not in file_bytes for secret in (b"old126", b"new126", b"dTpuZXcxMjY="))

    new_tunnels = new_proxy.connect_requests
    with read_only_file(result.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(result, CrawlOverrides(max_urls=None))

    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)
    assert "--proxy" in (caught.value.diagnostic.hint or "")
    assert "crawl.proxy" in (caught.value.diagnostic.hint or "")
    assert result.crawl_file.read_bytes() == file_bytes
    assert new_proxy.connect_requests == new_tunnels


@pytest.mark.parametrize(
    "fresh_proxy",
    ["***", "http://u:***@127.0.0.1:1", "u:%2A%2A%2A@127.0.0.1:1", "http://u:malformed126@["],
    ids=["whole-marker", "password-marker", "encoded-marker", "invalid-url"],
)
def test_unusable_fresh_proxy_is_refused_before_writer_or_network(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    fixture_proxy: StartProxy,
    fresh_proxy: str,
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    stopped = crawl_result(
        "http://site.test/", proxy=proxy.url.replace("http://", "http://u:old126@"), max_urls=1
    )
    assert stopped.summary.state == "stopped"
    config = json.loads(crawl_row(stopped.crawl_file)["config"])
    assert config["crawl"]["proxy"] == proxy.url.replace("http://", "http://u:***@")
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    requests = proxy.requests
    reporter = Collected()

    with read_only_file(stopped.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(stopped, CrawlOverrides(proxy=fresh_proxy), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "invalid_value",
        2,
        {"key": "crawl.proxy"},
    )
    diagnostic = json.dumps(caught.value.diagnostic.to_json())
    assert fresh_proxy not in diagnostic
    assert "malformed126" not in diagnostic
    assert reporter.events == []
    assert proxy.requests == requests
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files


@pytest.mark.parametrize("clear_explicit", [False, True], ids=["environment", "empty-override"])
def test_continue_uses_current_proxy_environment(
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
    clear_explicit: bool,
) -> None:
    hosts = fixture_tls_hosts(SHOP, Site({}))
    old_proxy = fixture_proxy(hosts.resolver, auth=("u", "old126"))
    new_proxy = fixture_proxy(hosts.resolver, auth=("u", "new126"))
    old_url = old_proxy.url.replace("http://", "http://u:old126@")
    monkeypatch.setenv("HTTPS_PROXY", old_url)
    monkeypatch.setenv("HTTP_PROXY", "http://unused.test:3128")
    monkeypatch.setenv("NO_PROXY", "old.test")
    stopped = crawl_result(
        "https://site.test/",
        proxy=old_url if clear_explicit else None,
        trust_anchors=hosts.trust_anchors,
        max_urls=1,
        retries=0,
        network_wait=0,
    )
    assert stopped.summary.state == "stopped"
    assert json.loads(crawl_row(stopped.crawl_file)["config"])["environment"] == {
        "https_proxy": old_proxy.url.replace("http://", "http://u:***@"),
        "http_proxy": "***",
        "no_proxy": "old.test",
    }
    old_tunnels = old_proxy.connect_requests
    origin_count = len(hosts.secure_site.requests)
    monkeypatch.setenv("https_proxy", new_proxy.url.replace("http://", "u:new126@"))
    monkeypatch.delenv("HTTP_PROXY")
    monkeypatch.setenv("NO_PROXY", "new.test")
    overrides = (
        CrawlOverrides(max_urls=None, proxy="") if clear_explicit else CrawlOverrides(max_urls=None)
    )

    result = continued(
        stopped, overrides, resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    )

    assert result.summary.state == "completed"
    assert old_proxy.connect_requests == old_tunnels
    assert {
        (entry.target, entry.headers.get("Proxy-Authorization"))
        for entry in new_proxy.connect_requests
    } == {("site.test:443", "Basic dTpuZXcxMjY=")}
    assert [request.path for request in hosts.secure_site.requests[origin_count:]] == [
        "/robots.txt",
        "/next",
        "/last",
    ]
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["crawl"]["proxy"] is None
    assert config["environment"] == {
        "https_proxy": new_proxy.url.replace("http://", "http://u:***@"),
        "no_proxy": "new.test",
    }
    assert b"new126" not in result.crawl_file.read_bytes()


class QuotingProxyResolver(AbstractResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise OSError(
            None, "refused http://u:fresh%3A126@proxy.test:3128 / fresh%3A126 / fresh:126; staging"
        )

    async def close(self) -> None:
        pass


def test_continue_masks_fresh_proxy_password_in_transport_failures(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(SHOP, Site({}))
    proxy = fixture_proxy(hosts.resolver)
    stopped = crawl_result(
        "http://site.test/",
        proxy=proxy.url.replace("http://", "http://u:old126@"),
        max_urls=1,
        retries=0,
        network_wait=0,
    )

    result = continued(
        stopped,
        CrawlOverrides(max_urls=None, proxy="http://u:fresh%3A126@proxy.test:3128"),
        resolver=QuotingProxyResolver(),
    )

    [(fetch_error, message)] = query(
        result.crawl_file,
        "SELECT fetch_error, fetch_error_message FROM urls WHERE url = 'http://site.test/next'",
    )
    [(robots_error, robots_message)] = query(
        result.crawl_file,
        "SELECT robots_fetch_error, robots_fetch_error_message FROM origins "
        "WHERE origin = 'http://site.test'",
    )
    assert (fetch_error, robots_error) == ("dns_error", "dns_error")
    for recorded_message in (message, robots_message):
        assert "refused *** / *** / ***; staging" in recorded_message
        assert "fresh%3A126" not in recorded_message
        assert "fresh:126" not in recorded_message
