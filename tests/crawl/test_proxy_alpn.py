"""Measure HTTPS capability through the Crawl's authenticated proxy route."""

import pytest

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import RequestLog, ServerHandle
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("explicit", [True, False], ids=["explicit-over-bypass", "environment"])
def test_the_alpn_probe_uses_its_own_authenticated_tunnel(
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
    explicit: bool,
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Secure shop</title>")}), Site({}), alpn=("h2", "http/1.1")
    )
    proxy = fixture_proxy(hosts.resolver, auth=("u", "pw"))
    other_proxy = fixture_proxy(hosts.resolver)
    proxy_url = "http://u:p%77@proxy.test:3128"
    resolver = FixtureResolver({("proxy.test", 3128): ServerHandle(proxy.url, RequestLog())})
    monkeypatch.setenv("HTTPS_PROXY", other_proxy.url)
    if explicit:
        monkeypatch.setenv("NO_PROXY", "*")
    else:
        monkeypatch.setenv("https_proxy", proxy_url)

    result = crawl_result(
        "https://site.test/",
        proxy=proxy_url if explicit else "",
        auth="alice:s3cret",
        header=["X-Env: staging"],
        resolver=resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert query(
        result.crawl_file, "SELECT url, fetch_error, status_code, attempt_count FROM urls"
    ) == [("https://site.test/", None, 200, 1)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]
    assert resolver.lookups == ("proxy.test", "proxy.test")
    assert (proxy.requests, other_proxy.requests, other_proxy.connect_requests) == ((), (), ())
    assert [
        (
            entry.method,
            entry.target,
            entry.headers.get("Proxy-Authorization"),
            entry.headers.get("Authorization"),
            entry.headers.get("X-Env"),
        )
        for entry in proxy.connect_requests
    ] == [
        ("CONNECT", "site.test:443", "Basic dTpwdw==", None, None),
        ("CONNECT", "site.test:443", "Basic dTpwdw==", None, None),
    ]
    assert [
        (
            request.method,
            request.path,
            request.http_version,
            request.alpn,
            request.headers.get("Authorization"),
            request.headers.get("X-Env"),
            request.headers.get("Proxy-Authorization"),
        )
        for request in hosts.secure_site.requests
    ] == [
        ("GET", "/robots.txt", (1, 1), None, "Basic YWxpY2U6czNjcmV0", "staging", None),
        ("GET", "/", (1, 1), None, "Basic YWxpY2U6czNjcmV0", "staging", None),
    ]
