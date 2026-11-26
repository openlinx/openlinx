"""Measure HTTPS capability through the Crawl's authenticated proxy route."""

import ssl

import pytest
import trustme

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import RequestLog, Serve, ServerHandle
from tests.fixture_site.tls import SniLog, StartTlsHosts
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


@pytest.mark.parametrize(
    ("proxy_certificate", "proxy_name", "dns_name"),
    [
        ("trusted", "proxy.test", "proxy.test"),
        ("trusted", "proxy.test.", "proxy.test."),
        ("trusted", "proxy.test..", "proxy.test."),
        ("untrusted", "proxy.test", "proxy.test"),
        ("wrong-name", "proxy.test", "proxy.test"),
    ],
    ids=["trusted", "absolute", "repeated-dot", "untrusted", "wrong-name"],
)
def test_the_alpn_probe_verifies_the_environment_proxy_before_connect(
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    fixture_proxy: StartProxy,
    monkeypatch: pytest.MonkeyPatch,
    proxy_certificate: str,
    proxy_name: str,
    dns_name: str,
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Secure shop</title>")}), Site({}), alpn=("h2", "http/1.1")
    )
    ca = trustme.CA()
    proxy_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificate_name = "other.test" if proxy_certificate == "wrong-name" else "proxy.test"
    ca.issue_cert(certificate_name).configure_cert(proxy_tls)
    sni = SniLog()
    proxy_tls.sni_callback = sni.record
    proxy = fixture_proxy(hosts.resolver, auth=("u", "pw"), tls=proxy_tls)
    resolver = FixtureResolver({(dns_name, 8443): ServerHandle(proxy.url, RequestLog())})
    monkeypatch.setenv("HTTPS_PROXY", f"https://u:pw@{proxy_name}:8443")
    anchors = hosts.trust_anchors
    if proxy_certificate != "untrusted":
        anchors += ca.cert_pem.bytes().decode("ascii")

    result = crawl_result(
        "https://site.test/", resolver=resolver, trust_anchors=anchors, retries=0, network_wait=0
    )

    urls = query(result.crawl_file, "SELECT fetch_error, status_code FROM urls")
    origins = query(result.crawl_file, "SELECT origin, http_version FROM origins")
    if proxy_certificate == "trusted":
        assert urls == [(None, 200)]
        assert origins == [("https://site.test", "http_2")]
        assert [
            (request.target, request.headers.get("Proxy-Authorization"))
            for request in proxy.connect_requests
        ] == [("site.test:443", "Basic dTpwdw=="), ("site.test:443", "Basic dTpwdw==")]
        assert [
            (request.method, request.path, request.http_version, request.alpn)
            for request in hosts.secure_site.requests
        ] == [("GET", "/robots.txt", (1, 1), None), ("GET", "/", (1, 1), None)]
    else:
        assert urls == [("tls_error", None)]
        assert origins == [("https://site.test", None)]
        assert proxy.connect_requests == ()
        assert hosts.secure_site.requests == ()
    assert resolver.lookups == (dns_name, dns_name)
    assert sni.names == ("proxy.test", "proxy.test")


@pytest.mark.parametrize(
    ("authority", "proxy_dns_name", "tls_name", "expected_sni"),
    [
        ("site.test.", "site.test.", "site.test", "site.test"),
        ("site.test..", "site.test..", "site.test", "site.test"),
        ("127.0.0.1", "127.0.0.1", "127.0.0.1", None),
        ("[::1]", "::1", "::1", None),
    ],
    ids=["absolute", "repeated-dot", "ipv4", "ipv6"],
)
def test_a_tunneled_origin_uses_the_same_tls_identity_as_the_probe(
    temp_workspace: TempWorkspace,
    fixture_site: Serve,
    fixture_proxy: StartProxy,
    authority: str,
    proxy_dns_name: str,
    tls_name: str,
    expected_sni: str | None,
) -> None:
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert(tls_name).configure_cert(tls)
    tls.set_alpn_protocols(["h2", "http/1.1"])
    sni = SniLog()
    tls.sni_callback = sni.record
    site = fixture_site(Site({"/": Page(body="<title>Home</title>")}), tls)
    proxy = fixture_proxy(FixtureResolver({(proxy_dns_name, 443): site}))

    result = crawl_result(
        f"https://{authority}/",
        proxy=proxy.url,
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        retries=0,
        network_wait=0,
    )

    assert query(result.crawl_file, "SELECT url, fetch_error, status_code FROM urls") == [
        (f"https://{authority}/", None, 200)
    ]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        (f"https://{authority}", "http_2")
    ]
    assert [request.target for request in proxy.connect_requests] == [
        f"{authority}:443",
        f"{authority}:443",
    ]
    assert sni.names == (expected_sni, expected_sni)
