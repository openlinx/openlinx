"""Verify where origin identity is sent when Crawls use HTTPS proxy tunnels."""

import ssl

import trustme

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace


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
