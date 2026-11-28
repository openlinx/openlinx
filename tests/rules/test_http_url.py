"""Verify the HTTP URL Warning on recorded responses through the Crawl and Store APIs."""

import pytest

from openlinx.crawl.urls import NormalizedUrl
from openlinx.rules.registry import RULES
from openlinx.store.issues import read_affected_urls
from openlinx.store.records import FetchedUrl, Provenance
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Redirect, Site, Status
from tests.fixture_site.tls import StartTlsHosts
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.workspace import TempWorkspace


@pytest.mark.usefixtures("temp_workspace")
def test_content_served_over_http(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/section/a": Page(
                    body='<title>Shop</title><h1>Shop</h1><a href="/outside">Outside Scope</a>'
                    '<a href="/section/300">300</a><a href="/section/excluded">Excluded</a>'
                    '<a href="http://other.test/a">External</a>'
                ),
                "/outside": Status(299, content_type="text/plain"),
                "/section/300": Status(300),
            }
        ),
        Site({"/a": Page(body="<title>External shop</title>")}),
    )
    result = crawl_result(
        "http://site.test/section/a",
        resolver=hosts.resolver,
        scope="subfolder",
        check_external=True,
        exclude=["/section/excluded$"],
    )
    assert result.summary.state == "completed"
    file = result.crawl_file
    rows = query(
        file,
        "SELECT id, url, is_internal, in_scope, fetch_state, status_code, parsed "
        "FROM urls ORDER BY url",
    )
    assert [row[1:] for row in rows] == [
        ("http://other.test/a", 0, 0, "fetched", 200, 0),
        ("http://site.test/outside", 1, 0, "fetched", 299, 0),
        ("http://site.test/section/300", 1, 1, "fetched", 300, 0),
        ("http://site.test/section/a", 1, 1, "fetched", 200, 1),
        ("http://site.test/section/excluded", 1, 0, "skipped", None, 0),
    ]
    assert query(
        file,
        "SELECT category, issue_type, priority, applies_to, enabled, thresholds "
        "FROM rules WHERE id = 'http-url'",
    ) == [("security", "warning", "high", "internal_urls", 1, "{}")]
    assert query(
        file,
        "SELECT category, issue_type, priority, affected_count FROM issues "
        "WHERE rule_id = 'http-url'",
    ) == [("security", "warning", "high", 2)]
    urls = {row[0]: row[1] for row in rows}
    assert sorted(
        (urls[row.url_id], row.detail) for row in read_affected_urls(file, "http-url", RULES)
    ) == [
        ("http://site.test/outside", {"status_code": 299}),
        ("http://site.test/section/a", {"status_code": 200}),
    ]
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = 'http-url'")
    assert sorted(query(file, sql)) == query(
        file, "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'http-url' ORDER BY url_id"
    )


@pytest.mark.usefixtures("temp_workspace")
def test_http_url_that_redirects_to_https(fixture_tls_hosts: StartTlsHosts) -> None:
    hosts = fixture_tls_hosts(
        Site(
            {
                "/b": Redirect("https://site.test/secure-b", status=301),
                "/secure-b": Page(body="<title>Secure shop</title><h1>Secure shop</h1>"),
            }
        ),
        Site({}),
    )
    result = crawl_result(
        "http://site.test/b", resolver=hosts.resolver, trust_anchors=hosts.trust_anchors
    )
    assert result.summary.state == "completed"
    file = result.crawl_file
    assert query(
        file,
        """SELECT source.url, source.is_internal, source.fetch_state, source.status_code, target.url
           FROM urls AS source LEFT JOIN urls AS target ON target.id = source.redirect_url_id
           ORDER BY source.url""",
    ) == [
        ("http://site.test/b", 1, "fetched", 301, "https://site.test/secure-b"),
        ("https://site.test/secure-b", 1, "fetched", 200, None),
    ]
    assert read_affected_urls(file, "http-url", RULES) == []
    assert query(file, "SELECT rule_id FROM issues WHERE rule_id = 'http-url'") == []


def test_http_url_excludes_informational_status(temp_workspace: TempWorkspace) -> None:
    # Record 199 directly because the Fetcher treats it as an interim response.
    seed = NormalizedUrl("http://example.com/")
    file = create_any_crawl(temp_workspace, seeds=[seed]).path
    with CrawlWriter(file, FakeClock()) as writer:
        url_id = writer.run(record_seed(seed, is_internal=True, in_scope=True))
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=url_id,
                    provenance=Provenance(
                        crawl_depth=0, discovered_via="seed", found_on_url_id=None
                    ),
                    status_code=199,
                    content_type=None,
                    fetched_at=STARTED_AT,
                    response_time_ms=1,
                    parsed=False,
                    attempt_count=1,
                    redirect=None,
                )
            )
        )

    assert query(file, "SELECT url, is_internal, fetch_state, status_code FROM urls") == [
        ("http://example.com/", 1, "fetched", 199)
    ]
    assert read_affected_urls(file, "http-url", RULES) == []
