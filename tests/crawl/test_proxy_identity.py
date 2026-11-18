"""Verify where origin identity is sent when Crawls use HTTPS proxy tunnels."""

import ssl

import pytest
import trustme

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import SniLog
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(
    ("seed_host", "dns_name", "port", "sni_name", "authority", "origin_host"),
    [
        ("site.test", "site.test", 443, "site.test", "site.test:443", "site.test"),
        ("site.test:4443", "site.test", 4443, "site.test", "site.test:4443", "site.test:4443"),
        ("site.test.", "site.test.", 443, "site.test", "site.test.:443", "site.test"),
        ("site.test.:4443", "site.test.", 4443, "site.test", "site.test.:4443", "site.test:4443"),
        ("127.0.0.1", "127.0.0.1", 443, None, "127.0.0.1:443", "127.0.0.1"),
        ("127.0.0.1:4443", "127.0.0.1", 4443, None, "127.0.0.1:4443", "127.0.0.1:4443"),
        ("[::1]", "::1", 443, None, "[::1]:443", "[::1]"),
        ("[::1]:4443", "::1", 4443, None, "[::1]:4443", "[::1]:4443"),
    ],
)
@pytest.mark.parametrize("host_override", [None, "staging-vhost.test"], ids=["default", "custom"])
def test_connect_host_matches_its_authority_without_changing_origin_identity(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    fixture_proxy: StartProxy,
    seed_host: str,
    dns_name: str,
    port: int,
    sni_name: str | None,
    authority: str,
    origin_host: str,
    host_override: str | None,
) -> None:
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert(sni_name or dns_name).configure_cert(tls)
    tls.set_alpn_protocols(["h2", "http/1.1"])
    sni = SniLog()
    tls.sni_callback = sni.record
    site = fixture_site(Site({"/entry": Page(body="<title>Origin</title>")}), tls)
    resolver = FixtureResolver({(dns_name, port): site})
    proxy = fixture_proxy(resolver, auth=("u", "pw"), strict_connect_host=True)
    seed = f"https://{seed_host}/entry?q=value"
    headers = ["X-Env: staging"]
    if host_override is not None:
        headers.append(f"Host: {host_override}")

    result = crawl_result(
        seed,
        proxy=proxy.url.replace("http://", "http://u:pw@"),
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        ignore_robots=True,
        auth="alice:s3cret",
        header=headers,
        retries=0,
        network_wait=0,
    )

    assert [
        (
            request.method,
            request.target,
            request.headers.getall("Host", []),
            request.headers.get("Proxy-Authorization"),
            request.headers.get("Authorization"),
            request.headers.get("X-Env"),
        )
        for request in proxy.connect_requests
    ] == [("CONNECT", authority, [authority], "Basic dTpwdw==", None, None)] * 2
    assert sni.names == (sni_name, sni_name)
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [(seed, 200)]
    assert query(result.crawl_file, "SELECT http_version FROM origins") == [("http_2",)]
    assert [
        (
            request.path,
            request.headers.get("Host"),
            request.headers.get("Authorization"),
            request.headers.get("X-Env"),
            request.headers.get("Proxy-Authorization"),
        )
        for request in site.requests
    ] == [
        ("/robots.txt", host_override or origin_host, "Basic YWxpY2U6czNjcmV0", "staging", None),
        ("/entry?q=value", host_override or origin_host, "Basic YWxpY2U6czNjcmV0", "staging", None),
    ]


def test_connect_does_not_carry_custom_origin_identity(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    fixture_proxy: StartProxy,
) -> None:
    ca = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ca.issue_cert("site.test", "other.test").configure_cert(tls)
    internal = fixture_site(
        Site({"/": Page(body='<a href="https://other.test/partner">Partner</a>')}), tls
    )
    external = fixture_site(Site({"/partner": Page(body="Partner")}), tls)
    resolver = FixtureResolver({("site.test", 443): internal, ("other.test", 443): external})
    proxy = fixture_proxy(resolver, auth=("u", "pw"))

    result = crawl_result(
        "https://site.test/",
        proxy=proxy.url.replace("http://", "http://u:pw@"),
        trust_anchors=ca.cert_pem.bytes().decode("ascii"),
        auth="alice:s3cret",
        header=["X-Env: staging", "Host: staging-vhost.test"],
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert {
        (
            request.method,
            request.target,
            tuple(host.removesuffix(":443") for host in request.headers.getall("Host", [])),
            tuple(request.headers.getall("Authorization", [])),
            tuple(request.headers.getall("X-Env", [])),
        )
        for request in proxy.connect_requests
    } == {
        ("CONNECT", "site.test:443", ("site.test",), (), ()),
        ("CONNECT", "other.test:443", ("other.test",), (), ()),
    }
    assert [
        (
            request.path,
            request.headers.get("Host"),
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
        )
        for request in internal.requests
    ] == [
        ("/robots.txt", "staging-vhost.test", ["Basic YWxpY2U6czNjcmV0"], ["staging"]),
        ("/", "staging-vhost.test", ["Basic YWxpY2U6czNjcmV0"], ["staging"]),
    ]
    assert sorted(
        (
            request.path,
            request.headers.get("Host"),
            request.headers.getall("Authorization", []),
            request.headers.getall("X-Env", []),
        )
        for request in external.requests
    ) == [("/partner", "other.test", [], []), ("/robots.txt", "other.test", [], [])]
