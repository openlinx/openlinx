"""TLS trust (022-add-fetch-policy D5, fetching spec: TLS certificate verification)."""

from openlinx.output.reporter import Collected
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
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

    assert (
        query(crawl_file, "SELECT url, fetch_state, status_code FROM urls"),
        query(crawl_file, "SELECT origin, http_version FROM origins"),
    ) == ([("https://site.test/", "fetched", 200)], [("https://site.test", None)])


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


def test_a_certificate_from_an_unknown_ca_is_a_tls_error(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        lambda untrusted_port: Site(
            routes={
                "/": Page(body=f'<a href="https://other.test:{untrusted_port}/">Partner shop</a>')
            }
        ),
        OTHER,
    )

    crawl_file = crawl_result(
        "http://site.test/", resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    ).crawl_file

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error FROM urls WHERE url = ?",
        [f"https://other.test:{hosts.untrusted_port}/"],
    ) == [("error", "tls_error")]


def test_a_self_signed_certificate_is_a_tls_error(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="https://selfsigned.test/">Partner shop</a> '
                    '<a href="https://site.test/">Secure home</a>'
                )
            }
        ),
        OTHER,
    )
    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
    )

    assert result.summary.state == "completed"
    assert query(
        result.crawl_file,
        "SELECT url, is_internal, fetch_state, fetch_error, status_code, attempt_count "
        "FROM urls WHERE url LIKE 'https:%' ORDER BY url",
    ) == [
        ("https://selfsigned.test/", 0, "error", "tls_error", None, 0),
        ("https://site.test/", 1, "fetched", None, 200, 1),
    ]
    assert hosts.selfsigned.requests == ()


def test_a_robots_txt_with_a_bad_certificate_gives_its_urls_tls_error_without_a_request(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)

    crawl_file = crawl_result(
        "https://badcert.test/", resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    ).crawl_file

    assert (
        query(
            crawl_file,
            "SELECT url, fetch_state, fetch_error, fetched_at, attempt_count FROM urls",
        ),
        hosts.badcert.requests,
    ) == ([("https://badcert.test/", "error", "tls_error", None, 0)], ())


def test_tls_errors_never_pause_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    hosts = [f"https://a{n}.site.test" for n in range(1, 13)]
    # Each subdomain's certificate fails to verify, for its robots.txt and its page alike: more
    # Internal failures in a row than pause the Crawl, if they counted.
    pages = {
        "https://site.test/": FakePage("".join(f'<a href="{host}/">A</a>' for host in hosts)),
        **{f"{host}/robots.txt": FakePage("", fails="tls_error") for host in hosts},
        **{f"{host}/": FakePage("", fails="tls_error") for host in hosts},
    }

    result = crawl_result(
        "https://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages),
        reporter=reporter,
        scope="subdomains",
        network_wait=0,
    )

    assert (
        result.summary.state,
        result.summary.stop_reason,
        [name for name, _ in reporter.events if name == "crawl_paused"],
    ) == ("completed", None, [])
