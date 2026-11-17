"""Verify the HTTP capability recorded by a Crawl of real fixture origins."""

import sqlite3
from contextlib import closing
from pathlib import Path

from openlinx.services.crawling import CrawlOverrides
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SITE = Site({"/": Page(body='<a href="http://other.test/partner">Partner</a>')})
OTHER = Site({"/partner": Page(body="<title>Partner</title>")})


def test_an_origin_that_selects_http_2(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Home</title>")}), OTHER, alpn=("h2", "http/1.1")
    )

    result = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    requests = hosts.secure_site.requests
    assert [(request.method, request.path, request.http_version) for request in requests] == [
        ("GET", "/robots.txt", (1, 1)),
        ("GET", "/", (1, 1)),
    ]
    assert all(request.alpn != "h2" for request in requests)
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]


def test_an_origin_that_offers_only_http_1_1(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    crawl_file = _crawl_https(fixture_tls_hosts, alpn=("http/1.1",))

    assert query(crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_1_1")
    ]


def test_a_listener_with_no_alpn_selection_is_http_1_1_capable(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    crawl_file = _crawl_https(fixture_tls_hosts, alpn=())

    assert query(crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_1_1")
    ]


def _crawl_https(fixture_tls_hosts: StartTlsHosts, *, alpn: tuple[str, ...]) -> Path:
    hosts = fixture_tls_hosts(Site({"/": Page(body="<title>Home</title>")}), OTHER, alpn=alpn)
    result = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    return result.crawl_file


def test_a_plain_http_origin(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, fixture_proxy: StartProxy
) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    proxy = fixture_proxy(hosts.resolver)

    result = crawl_result(
        "http://site.test/",
        proxy=proxy.url,
        check_external=False,
        retries=0,
        network_wait=0,
    )

    assert result.summary.state == "completed"
    assert proxy.requests == ("http://site.test/robots.txt", "http://site.test/")
    assert proxy.connect_requests == ()
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins ORDER BY origin") == [
        ("http://other.test", None),
        ("http://site.test", "http_1_1"),
    ]
    assert query(result.crawl_file, "SELECT http_version FROM pages") == [(None,)]


def test_continuing_a_crawl_with_unmeasured_origins_records_only_newly_requested_ones(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(SITE, OTHER)
    stopped = crawl_result(
        "http://site.test/", resolver=hosts.resolver, max_urls=1, retries=0, network_wait=0
    )
    assert (
        stopped.summary.state,
        stopped.summary.stop_reason,
        [request.path for request in hosts.other.requests],
    ) == ("stopped", "max_urls", [])
    # Schema v1 already had the column; a Crawl written before measurement held NULL in it.
    with closing(sqlite3.connect(stopped.crawl_file)) as connection:
        connection.execute("UPDATE origins SET http_version = NULL")
        connection.commit()

    result = continued(stopped, CrawlOverrides(max_urls=None), resolver=hosts.resolver)

    assert result.summary.state == "completed"
    assert [request.path for request in hosts.site.requests] == ["/robots.txt", "/"]
    assert [request.path for request in hosts.other.requests] == ["/robots.txt", "/partner"]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins ORDER BY origin") == [
        ("http://other.test", "http_1_1"),
        ("http://site.test", None),
    ]
    assert query(result.crawl_file, "SELECT schema_version FROM crawl") == [(1,)]
    assert query(result.crawl_file, "PRAGMA user_version") == [(1,)]
