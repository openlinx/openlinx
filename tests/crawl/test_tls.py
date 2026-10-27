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


def test_a_certificate_for_another_name_is_a_tls_error(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="https://badcert.test/">Sale</a> '
                    '<a href="https://site.test/">Secure home</a>'
                )
            }
        ),
        OTHER,
    )

    crawl_file = crawl_result(
        "http://site.test/", resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    ).crawl_file

    assert query(
        crawl_file,
        "SELECT url, fetch_state, fetch_error FROM urls WHERE url LIKE 'https:%' ORDER BY url",
    ) == [("https://badcert.test/", "error", "tls_error"), ("https://site.test/", "fetched", None)]
