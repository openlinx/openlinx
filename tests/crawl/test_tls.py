"""TLS trust (022-add-fetch-policy D5, fetching spec: TLS certificate verification)."""

from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

SITE = Site(routes={"/": Page(body="<p>Site</p>")})
OTHER = Site(routes={"/": Page(body="<p>Other</p>")})


def test_an_https_site_signed_by_a_ca_the_crawl_trusts_is_crawled(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)

    crawl_file = crawl_result(
        "https://site.test/", resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    ).crawl_file

    assert query(crawl_file, "SELECT url, fetch_state, status_code FROM urls") == [
        ("https://site.test/", "fetched", 200)
    ]
