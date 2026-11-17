"""Verify the HTTP capability recorded by a Crawl of real fixture origins."""

import sqlite3
from contextlib import closing

from openlinx.services.crawling import CrawlOverrides
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

SITE = Site({"/": Page(body='<a href="http://other.test/partner">Partner</a>')})
OTHER = Site({"/partner": Page(body="<title>Partner</title>")})


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
