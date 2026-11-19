"""Verify response-code Rules over URLs written by a real Crawl."""

import json

import pytest

from openlinx.rules.response_codes import INTERNAL_4XX, INTERNAL_5XX
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query


@pytest.mark.usefixtures("temp_workspace")
def test_client_error(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/section/": Page(
                    body='<a href="/gone">Gone</a>'
                    '<a href="/section/before">Before the range</a>'
                    '<a href="/section/first">First client error</a>'
                    '<a href="/section/last">Last client error</a>'
                    '<a href="/section/after">After the range</a>'
                ),
                "/gone": Status(404, body="Not found"),
                "/section/before": Status(399),
                "/section/first": Status(400),
                "/section/last": Status(499),
                "/section/after": Status(500),
            }
        )
    )
    file = crawled(server.url("/section/"), "--scope", "subfolder", "--retries", "0")
    statuses = query(
        file,
        "SELECT id, is_internal, in_scope, fetch_state, status_code FROM urls "
        "WHERE url != ? ORDER BY status_code",
        (server.url("/section/"),),
    )
    assert [row[1:] for row in statuses] == [
        (1, 1, "fetched", 399),
        (1, 1, "fetched", 400),
        (1, 0, "fetched", 404),
        (1, 1, "fetched", 499),
        (1, 1, "fetched", 500),
    ]
    _, first, gone, last, _ = (row[0] for row in statuses)
    affected = evaluate_rule(file, INTERNAL_4XX)

    assert sorted(affected, key=lambda row: row.url_id) == sorted(
        [
            AffectedUrl(url_id=first, detail={"status_code": 400}),
            AffectedUrl(url_id=gone, detail={"status_code": 404}),
            AffectedUrl(url_id=last, detail={"status_code": 499}),
        ],
        key=lambda row: row.url_id,
    )


@pytest.mark.usefixtures("temp_workspace")
def test_external_urls_are_not_internal_urls(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body='<a href="/gone">Internal</a><a href="http://other.test/gone">External</a>'
                ),
                "/gone": Status(404),
            }
        ),
        Site({"/gone": Status(404)}),
    )
    file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file
    urls = query(
        file,
        "SELECT id, url, is_internal, fetch_state, status_code FROM urls "
        "WHERE status_code = 404 ORDER BY url",
    )
    assert [row[1:] for row in urls] == [
        ("http://other.test/gone", 0, "fetched", 404),
        ("http://site.test/gone", 1, "fetched", 404),
    ]
    internal_id = urls[1][0]

    assert evaluate_rule(file, INTERNAL_4XX) == [
        AffectedUrl(url_id=internal_id, detail={"status_code": 404})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_client_error_recorded_by_a_crawl(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/gone">Gone</a>'),
                "/gone": Status(404, body="Not found", content_type="text/plain"),
            }
        )
    )
    file = crawled(server.url("/"))
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    url = server.url("/gone")
    assert query(
        file,
        """SELECT is_internal, fetch_state, status_code, content_type, parsed,
                  EXISTS(SELECT 1 FROM pages WHERE pages.url_id = urls.id)
           FROM urls WHERE url = ?""",
        (url,),
    ) == [(1, "fetched", 404, "text/plain", 0, 0)]

    affected = query(
        file,
        """SELECT urls.url, affected_urls.detail
           FROM affected_urls JOIN urls ON urls.id = affected_urls.url_id
           WHERE affected_urls.rule_id = 'internal-4xx'""",
    )
    assert [(affected_url, json.loads(detail)) for affected_url, detail in affected] == [
        (url, {"status_code": 404})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_server_error(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body='<a href="/499">Before</a><a href="/500">First</a>'
                    '<a href="/503">Unavailable</a><a href="/599">Last</a>'
                    '<a href="/600">After</a><a href="http://other.test/503">External</a>'
                ),
                "/499": Status(499),
                "/500": Status(500),
                "/503": Status(503),
                "/599": Status(599),
                "/600": Status(600),
            }
        ),
        Site({"/503": Status(503)}),
    )
    file = crawl_result("http://site.test/", resolver=hosts.resolver, retries=0).crawl_file
    rows = query(
        file,
        "SELECT url, id, status_code FROM urls WHERE status_code >= 499 ORDER BY url",
    )
    assert [(url, code) for url, _, code in rows] == [
        ("http://other.test/503", 503),
        ("http://site.test/499", 499),
        ("http://site.test/500", 500),
        ("http://site.test/503", 503),
        ("http://site.test/599", 599),
        ("http://site.test/600", 600),
    ]
    urls = {url_id: url for url, url_id, _ in rows}

    assert sorted((urls[row.url_id], row.detail) for row in evaluate_rule(file, INTERNAL_5XX)) == [
        ("http://site.test/500", {"status_code": 500}),
        ("http://site.test/503", {"status_code": 503}),
        ("http://site.test/599", {"status_code": 599}),
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_no_response(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/slow">Slow</a>'), "/slow": Page(body="Late", delay=3)})
    )
    result = crawl_result(server.url("/"), timeout=1, retries=0)
    rows = query(
        result.crawl_file,
        "SELECT id, fetch_state, fetch_error FROM urls WHERE url = ?",
        (server.url("/slow"),),
    )
    [(slow_id, state, reason)] = rows
    assert (state, reason, result.summary.state) == ("error", "timeout", "completed")
    affected = query(
        result.crawl_file,
        "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'internal-no-response'",
    )
    assert [(url_id, json.loads(detail)) for url_id, detail in affected] == [
        (slow_id, {"error": "timeout"})
    ]
