"""Verify response-code Rules over URLs written by a real Crawl."""

import json
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from operator import itemgetter
from pathlib import Path

import pytest

from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.extract.link_handler import link_rows
from openlinx.extract.page_handler import page_rows
from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from openlinx.rules.registry import RULES
from openlinx.rules.response_codes import (
    INTERNAL_4XX,
    INTERNAL_5XX,
    INTERNAL_NO_RESPONSE,
    REDIRECT_CHAIN,
)
from openlinx.store.connections import connect
from openlinx.store.issues import evaluate_rule, read_affected_urls
from openlinx.store.links import write_links
from openlinx.store.pages import write_pages
from openlinx.store.records import AffectedUrl, FetchedUrl, NewUrl, Provenance, QueuedUrl
from openlinx.store.records import Redirect as RecordedRedirect
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import queued_batch, record_fetched, record_seed, record_unwritten
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site, Status
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.page_data import page_result
from tests.support.workspace import TempWorkspace


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
def test_server_error_raises_an_issue(fixture_hosts: StartHosts) -> None:
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
    assert evaluate_rule(result.crawl_file, INTERNAL_NO_RESPONSE) == [
        AffectedUrl(url_id=slow_id, detail={"error": "timeout"})
    ]
    affected = query(
        result.crawl_file,
        "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'internal-no-response'",
    )
    assert [(url_id, json.loads(detail)) for url_id, detail in affected] == [
        (slow_id, {"error": "timeout"})
    ]


def test_a_url_that_failed_to_be_recorded_is_no_issue(temp_workspace: TempWorkspace) -> None:
    file = create_any_crawl(temp_workspace).path
    with CrawlWriter(file, FakeClock()) as writer:
        url_id = writer.run(
            record_seed(NormalizedUrl("https://example.com/"), is_internal=True, in_scope=True)
        )
        writer.run(
            record_unwritten(
                url_id,
                "A response row could not be written.",
                blocked_by_robots_txt=False,
                attempt_count=1,
                provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
            )
        )

    assert query(file, "SELECT fetch_state, fetch_error FROM urls WHERE id = ?", (url_id,)) == [
        ("error", "record_failed")
    ]
    assert evaluate_rule(file, INTERNAL_NO_RESPONSE) == []


@pytest.mark.usefixtures("temp_workspace")
@pytest.mark.parametrize(
    ("ignore_robots", "blocked", "unanswered"),
    [
        pytest.param(
            False,
            ("skipped", "blocked_by_robots_txt", None, None),
            ("skipped", "blocked_by_robots_txt", None, None),
            id="respects-robots",
        ),
        pytest.param(
            True, ("fetched", None, 200, None), ("error", None, None, "timeout"), id="ignore-robots"
        ),
    ],
)
def test_blocked_even_when_crawled_anyway(
    fixture_hosts: StartHosts,
    ignore_robots: bool,
    blocked: tuple[str, str | None, int | None, str | None],
    unanswered: tuple[str, str | None, int | None, str | None],
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/robots.txt": Robots(
                    "User-agent: *\nDisallow: /private/\nDisallow: /section/private/\n"
                ),
                "/section/": Page(
                    body='<a href="/private/a">Outside Scope</a>'
                    '<a href="/section/private/unanswered">No response</a>'
                    '<a href="/section/allowed">Allowed</a>'
                    '<a href="/section/unchecked">Excluded</a>'
                    '<a href="http://other.test/private/a">External</a>'
                ),
                "/private/a": Status(200),
                "/section/private/unanswered": Status(200, hang=True),
                "/section/allowed": Status(200),
            }
        ),
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nDisallow: /private/\n"),
                "/private/a": Status(200),
            }
        ),
    )
    result = crawl_result(
        "http://site.test/section/",
        resolver=hosts.resolver,
        scope="subfolder",
        exclude=["/section/unchecked$"],
        ignore_robots=ignore_robots,
        timeout=1,
        retries=0,
    )
    assert result.summary.state == "completed"
    file = result.crawl_file
    rows = query(
        file,
        "SELECT id, url, is_internal, in_scope, blocked_by_robots_txt, fetch_state, "
        "skip_reason, status_code, fetch_error FROM urls ORDER BY url",
    )
    assert [row[1:] for row in rows] == [
        ("http://other.test/private/a", 0, 0, 1, *blocked),
        ("http://site.test/private/a", 1, 0, 1, *blocked),
        ("http://site.test/section/", 1, 1, 0, "fetched", None, 200, None),
        ("http://site.test/section/allowed", 1, 1, 0, "fetched", None, 200, None),
        ("http://site.test/section/private/unanswered", 1, 1, 1, *unanswered),
        ("http://site.test/section/unchecked", 1, 0, None, "skipped", "excluded", None, None),
    ]

    rule_id = "internal-blocked-by-robots-txt"
    matching = [rule for rule in RULES if rule.id == rule_id]
    assert len(matching) == 1, f"The catalogue must register {rule_id} once"
    [rule] = matching
    assert query(
        file,
        "SELECT category, issue_type, priority, applies_to, enabled, thresholds "
        "FROM rules WHERE id = ?",
        (rule_id,),
    ) == [("response_codes", "warning", "medium", "internal_urls", 1, "{}")]

    urls = {url_id: url for url_id, url, *_ in rows}
    expected = [
        ("http://site.test/private/a", None),
        ("http://site.test/section/private/unanswered", None),
    ]
    affected = [(urls[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=lambda item: item[0]) == expected
    assert (
        query(
            file,
            "SELECT urls.url, affected_urls.detail FROM affected_urls "
            "JOIN urls ON urls.id = affected_urls.url_id WHERE affected_urls.rule_id = ? "
            "ORDER BY urls.url",
            (rule_id,),
        )
        == expected
    )


@pytest.mark.usefixtures("temp_workspace")
def test_internal_redirect(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/section/": Page(
                    body='<a href="/section/old">Old</a>'
                    '<a href="/section/partner">Partner</a>'
                    '<a href="/section/299">Before the range</a>'
                    '<a href="/section/300">First</a>'
                    '<a href="/399">Last, outside Scope</a>'
                    '<a href="/section/400">After the range</a>'
                    '<a href="/section/excluded">Excluded</a>'
                ),
                "/section/old": Redirect("new", status=301),
                "/section/new": Page(body="<title>New</title>"),
                "/section/partner": Redirect("http://other.test/moved", status=302),
                "/section/299": Status(299),
                "/section/300": Redirect("new", status=300),
                "/399": Status(399),
                "/section/400": Status(400),
            }
        ),
        Site({"/moved": Redirect("http://site.test/section/new", status=302)}),
    )
    result = crawl_result(
        "http://site.test/section/",
        resolver=hosts.resolver,
        scope="subfolder",
        exclude=["/section/excluded$"],
        check_external=True,
        retries=0,
    )
    assert result.summary.state == "completed"
    file = result.crawl_file
    rows = query(
        file,
        """SELECT source.id, source.url, source.is_internal, source.in_scope, source.fetch_state,
                  source.status_code, source.redirect_location, target.url
           FROM urls AS source LEFT JOIN urls AS target ON target.id = source.redirect_url_id
           ORDER BY source.url""",
    )
    assert [row[1:] for row in rows] == [
        (
            "http://other.test/moved",
            0,
            0,
            "fetched",
            302,
            "http://site.test/section/new",
            "http://site.test/section/new",
        ),
        ("http://site.test/399", 1, 0, "fetched", 399, None, None),
        ("http://site.test/section/", 1, 1, "fetched", 200, None, None),
        ("http://site.test/section/299", 1, 1, "fetched", 299, None, None),
        ("http://site.test/section/300", 1, 1, "fetched", 300, "new", None),
        ("http://site.test/section/400", 1, 1, "fetched", 400, None, None),
        ("http://site.test/section/excluded", 1, 0, "skipped", None, None, None),
        ("http://site.test/section/new", 1, 1, "fetched", 200, None, None),
        (
            "http://site.test/section/old",
            1,
            1,
            "fetched",
            301,
            "new",
            "http://site.test/section/new",
        ),
        (
            "http://site.test/section/partner",
            1,
            1,
            "fetched",
            302,
            "http://other.test/moved",
            "http://other.test/moved",
        ),
    ]

    rule_id = "internal-3xx"
    matching = [rule for rule in RULES if rule.id == rule_id]
    assert len(matching) == 1, f"The catalogue must register {rule_id} once"
    [rule] = matching
    assert query(
        file,
        "SELECT category, issue_type, priority, applies_to, enabled, thresholds "
        "FROM rules WHERE id = ?",
        (rule_id,),
    ) == [("response_codes", "warning", "low", "internal_urls", 1, "{}")]

    expected = [
        ("http://site.test/399", {"status_code": 399, "redirect_url": None}),
        ("http://site.test/section/300", {"status_code": 300, "redirect_url": None}),
        (
            "http://site.test/section/old",
            {"status_code": 301, "redirect_url": "http://site.test/section/new"},
        ),
        (
            "http://site.test/section/partner",
            {"status_code": 302, "redirect_url": "http://other.test/moved"},
        ),
    ]
    urls = {url_id: url for url_id, url, *_ in rows}
    affected = [(urls[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=itemgetter(0)) == expected

    stored = query(
        file,
        "SELECT urls.url, affected_urls.detail FROM affected_urls "
        "JOIN urls ON urls.id = affected_urls.url_id WHERE affected_urls.rule_id = ? "
        "ORDER BY urls.url",
        (rule_id,),
    )
    assert [(url, json.loads(detail)) for url, detail in stored] == expected
    assert query(
        file,
        "SELECT category, issue_type, priority, affected_count FROM issues WHERE rule_id = ?",
        (rule_id,),
    ) == [("response_codes", "warning", "low", 4)]

    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,))
    with closing(connect(file, read_only=True)) as connection:
        reproduced = connection.execute(sql)
        assert tuple(column[0] for column in reproduced.description) == ("url_id", "detail")
        assert (
            sorted(
                ((urls[url_id], json.loads(detail)) for url_id, detail in reproduced),
                key=itemgetter(0),
            )
            == expected
        )


@pytest.fixture
def two_hop_site(fixture_site: StartSite) -> str:
    server = fixture_site(
        Site(
            {
                "/a": Redirect("/b", status=301),
                "/b": Redirect("/c", status=308),
                "/c": Page(body="<title>Destination</title>"),
            }
        )
    )
    return server.url("/")


def _redirect_chain_rows(file: Path) -> list[tuple[str, dict[str, object]]]:
    [rule] = [rule for rule in RULES if rule.id == "redirect-chain"]
    urls = dict(query(file, "SELECT id, url FROM urls"))
    stored = read_affected_urls(file, "redirect-chain", RULES)
    assert sorted(evaluate_rule(file, rule), key=lambda row: row.url_id) == stored
    with closing(connect(file, read_only=True)) as connection:
        (sql,) = connection.execute(
            "SELECT reproduce_sql FROM rules WHERE id = 'redirect-chain'"
        ).fetchone()
        reproduced = connection.execute(sql)
        assert tuple(column[0] for column in reproduced.description) == ("url_id", "detail")
        assert sorted((url_id, json.loads(detail)) for url_id, detail in reproduced) == [
            (row.url_id, row.detail) for row in stored
        ]
    return sorted(
        (urls[url_id], json.loads(detail))
        for url_id, detail in query(
            file,
            "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'redirect-chain'",
        )
    )


@pytest.mark.usefixtures("temp_workspace")
def test_two_hop_chain(two_hop_site: str) -> None:
    result = crawl_result(two_hop_site + "a")
    assert result.summary.state == "completed"
    file = result.crawl_file
    assert query(
        file,
        "SELECT category, issue_type, priority, applies_to, enabled, thresholds "
        "FROM rules WHERE id = 'redirect-chain'",
    ) == [("response_codes", "warning", "medium", "internal_urls", 1, '{"max_hops":1}')]
    assert _redirect_chain_rows(file) == [
        (two_hop_site + "a", {"hops": 2, "final_url": two_hop_site + "c"})
    ]
    assert query(file, "SELECT affected_count FROM issues WHERE rule_id = 'redirect-chain'") == [
        (1,)
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_one_hop_is_not_a_chain(two_hop_site: str) -> None:
    result = crawl_result(two_hop_site + "b")
    file = result.crawl_file
    assert query(file, "SELECT url, status_code FROM urls ORDER BY url") == [
        (two_hop_site + "b", 308),
        (two_hop_site + "c", 200),
    ]
    assert _redirect_chain_rows(file) == []


@pytest.mark.parametrize(
    ("max_hops", "affected"),
    [
        ("0", [("a", 2), ("b", 1)]),
        ("2", []),
        ("9" * 4300, []),
    ],
    ids=("zero", "equal-to-length", "largest-supported"),
)
def test_redirect_chain_uses_the_recorded_max_hops(
    temp_workspace: TempWorkspace,
    two_hop_site: str,
    max_hops: str,
    affected: list[tuple[str, int]],
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        f"[rules.redirect-chain]\nmax_hops = {max_hops}\n", encoding="utf-8"
    )
    file = crawl_result(two_hop_site + "a").crawl_file
    [(thresholds,)] = query(file, "SELECT thresholds FROM rules WHERE id = 'redirect-chain'")
    assert json.loads(thresholds) == {"max_hops": int(max_hops)}
    assert _redirect_chain_rows(file) == [
        (two_hop_site + path, {"hops": hops, "final_url": two_hop_site + "c"})
        for path, hops in affected
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_redirect_chain_stops_at_the_first_terminal_or_repeated_url(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<a href="/cut">Cut short</a><a href="/entry">Enters loop</a>'
                    '<a href="/missing">No further target</a><a href="/self">Self redirect</a>'
                    '<a href="/tail">Joins the entry to the loop</a>'
                ),
                "/cut": Redirect("/before-cut"),
                "/before-cut": Redirect("/unrequested"),
                "/unrequested": Page(body="Outside the Crawl"),
                "/entry": Redirect("/x"),
                "/x": Redirect("/y"),
                "/y": Redirect("/x"),
                "/tail": Redirect("/entry"),
                "/missing": Redirect("/last-3xx"),
                "/last-3xx": Redirect("/unused", status=300),
                "/self": Redirect("/self"),
            }
        )
    )
    result = crawl_result(server.url("/"), exclude=["/unrequested$"])
    assert result.summary.state == "completed"
    file = result.crawl_file
    assert query(
        file,
        "SELECT fetch_state, status_code FROM urls WHERE url = ?",
        (server.url("/unrequested"),),
    ) == [("skipped", None)]
    assert _redirect_chain_rows(file) == [
        (server.url("/cut"), {"hops": 2, "final_url": server.url("/unrequested")}),
        (server.url("/entry"), {"hops": 3, "final_url": server.url("/x")}),
        (server.url("/missing"), {"hops": 2, "final_url": server.url("/last-3xx")}),
        (server.url("/tail"), {"hops": 4, "final_url": server.url("/x")}),
        (server.url("/x"), {"hops": 2, "final_url": server.url("/x")}),
        (server.url("/y"), {"hops": 2, "final_url": server.url("/y")}),
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("-1", id="negative"),
        pytest.param("true", id="boolean"),
        pytest.param("1.5", id="fraction"),
        pytest.param("1" + "0" * 4300, id="too-large"),
    ],
)
def test_invalid_max_hops_fail_before_the_crawl_requests_a_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite, value: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Seed")}))
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        f"[rules.redirect-chain]\nmax_hops = {value}\n", encoding="utf-8"
    )
    with pytest.raises(OpenLinxError) as caught:
        crawl_result(server.url("/"))
    diagnostic = caught.value.diagnostic
    assert diagnostic.code == "settings_invalid"
    assert [error["key"] for error in diagnostic.details["errors"]] == [
        "rules.redirect-chain.max_hops"
    ]
    assert not server.requests


@pytest.mark.usefixtures("temp_workspace")
def test_redirect_chain_can_pass_through_external_urls(fixture_hosts: StartHosts) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/start">Start</a>'),
                "/start": Redirect("http://other.test/moved"),
                "/end": Status(410),
            }
        ),
        Site(
            {
                "/moved": Redirect("/moved-again"),
                "/moved-again": Redirect("http://site.test/end"),
            }
        ),
    )
    result = crawl_result("http://site.test/", resolver=hosts.resolver)
    assert result.summary.state == "completed"
    assert _redirect_chain_rows(result.crawl_file) == [
        ("http://site.test/start", {"hops": 3, "final_url": "http://site.test/end"})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_redirect_chain_reads_recorded_hops_beyond_the_crawl_hop_limit(
    fixture_site: StartSite,
) -> None:
    # Each URL was also linked from the Seed, so it can have its own recorded response.
    routes = {f"/r{index}": Redirect(f"/r{index + 1}") for index in range(1, 61)}
    server = fixture_site(
        Site(
            {
                **routes,
                "/": Page(body="".join(f'<a href="{path}">Hop</a>' for path in routes)),
                "/r61": Status(200),
            }
        )
    )
    result = crawl_result(server.url("/"), max_redirects=50)
    assert result.summary.state == "completed"
    rows = dict(_redirect_chain_rows(result.crawl_file))
    assert len(rows) == 59
    assert rows[server.url("/r1")] == {"hops": 60, "final_url": server.url("/r61")}
    assert rows[server.url("/r59")] == {"hops": 2, "final_url": server.url("/r61")}


def _record_redirect_graph(
    writer: CrawlWriter,
    source: QueuedUrl,
    edges: dict[int, int],
    urls: dict[int, NormalizedUrl],
    next_source: NormalizedUrl | None,
) -> dict[int, QueuedUrl]:
    # Discover every graph URL through a Link, in ID order, before recording its redirect.
    # Redirects can then exceed the Crawl's hop limit in aggregate, as each request starts
    # from a Link. The first Page also links to the Page that will discover the larger graph.
    targets = list(urls.values())
    if next_source is not None:
        targets.append(next_source)
    body = "".join(f'<a href="{target}">Next</a>' for target in targets)
    page = page_result(body, url=source.url, content_type="text/html")
    assert page.response is not None
    at = STARTED_AT + timedelta(seconds=2 * source.crawl_depth + 1)
    page = replace(page, url_id=source.id, response=replace(page.response, fetched_at=at))
    writer.run(
        record_fetched(
            FetchedUrl(
                url_id=source.id,
                provenance=Provenance(
                    crawl_depth=source.crawl_depth,
                    discovered_via=source.discovered_via,
                    found_on_url_id=source.found_on_url_id,
                ),
                status_code=200,
                content_type="text/html",
                fetched_at=at,
                response_time_ms=1,
                parsed=True,
                attempt_count=1,
                redirect=None,
                discovered=tuple(
                    NewUrl(
                        url=link.target, discovered_via="hyperlink", is_internal=True, in_scope=True
                    )
                    for link in page.links
                ),
                rows=(
                    HandlerRows(write_pages, tuple(page_rows(page))),
                    HandlerRows(write_links, tuple(link_rows(page))),
                ),
            )
        )
    )
    queued = writer.run(queued_batch(source.crawl_depth + 1, 0, len(targets), 1))
    assert [node.url for node in queued] == targets
    nodes = dict(zip(urls, queued[: len(urls)], strict=True))
    for start, target in edges.items():
        node = nodes[start]
        location = nodes[target].url
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=node.id,
                    provenance=Provenance(
                        crawl_depth=node.crawl_depth,
                        discovered_via=node.discovered_via,
                        found_on_url_id=node.found_on_url_id,
                    ),
                    status_code=301,
                    content_type=None,
                    fetched_at=at + timedelta(seconds=1),
                    response_time_ms=1,
                    parsed=False,
                    attempt_count=1,
                    redirect=RecordedRedirect(
                        location=location,
                        max_redirects=1,
                        target=NewUrl(
                            url=location, discovered_via="redirect", is_internal=True, in_scope=True
                        ),
                    ),
                )
            )
        )
    return nodes


@pytest.mark.parametrize(
    ("shape", "examples"),
    [
        (
            "interleaved cycle",
            {
                "http://127.0.0.1/128/1": (128, "http://127.0.0.1/128/1"),
                "http://127.0.0.1/128/65": (128, "http://127.0.0.1/128/65"),
                "http://127.0.0.1/128/128": (128, "http://127.0.0.1/128/128"),
                "http://127.0.0.1/256/1": (256, "http://127.0.0.1/256/1"),
                "http://127.0.0.1/256/129": (256, "http://127.0.0.1/256/129"),
                "http://127.0.0.1/256/256": (256, "http://127.0.0.1/256/256"),
            },
        ),
        (
            "shared tail",
            {
                "http://127.0.0.1/128/1": (64, "http://127.0.0.1/128/63"),
                "http://127.0.0.1/128/64": (2, "http://127.0.0.1/128/64"),
                "http://127.0.0.1/128/65": (65, "http://127.0.0.1/128/63"),
                "http://127.0.0.1/128/128": (3, "http://127.0.0.1/128/64"),
                "http://127.0.0.1/256/1": (128, "http://127.0.0.1/256/127"),
                "http://127.0.0.1/256/128": (2, "http://127.0.0.1/256/128"),
                "http://127.0.0.1/256/129": (129, "http://127.0.0.1/256/127"),
                "http://127.0.0.1/256/256": (3, "http://127.0.0.1/256/128"),
            },
        ),
    ],
    ids=["interleaved-cycle", "shared-tail"],
)
def test_recorded_redirect_chain_sql_keeps_its_vm_budget(
    temp_workspace: TempWorkspace, shape: str, examples: dict[str, tuple[int, str]]
) -> None:
    seed = NormalizedUrl("http://127.0.0.1/")
    more = NormalizedUrl(f"{seed}more")
    file = create_any_crawl(
        temp_workspace,
        seeds=[seed],
        command_argv=["linx", "crawl", seed, "--max-redirects", "1"],
        scope=scope_rules(seed).to_json(),
        config={"crawl": {"max_redirects": 1}},
    ).path

    def record_graph(
        size: int, source_depth: int, next_source: NormalizedUrl | None
    ) -> list[AffectedUrl]:
        half = size // 2
        if shape == "interleaved cycle":
            order = [url_id for i in range(1, half + 1) for url_id in (i, i + half)]
            edges = dict(zip(order, order[1:] + order[:1], strict=True))
        else:
            edges = {i: i + 1 for i in range(1, half)} | {half: half - 1}
            edges.update({i + half: i for i in range(1, half + 1)})

        urls = {i: NormalizedUrl(f"{seed}{size}/{i}") for i in sorted(edges)}
        with CrawlWriter(file, FakeClock()) as writer:
            if source_depth == 0:
                writer.run(record_seed(seed, is_internal=True, in_scope=True))
            (source,) = writer.run(queued_batch(source_depth, 0, 1, 1))
            nodes = _record_redirect_graph(writer, source, edges, urls, next_source)

        # Each member of the interleaved cycle repeats itself after `size` hops.
        if shape == "interleaved cycle":
            return [
                AffectedUrl(url_id=nodes[index].id, detail={"hops": size, "final_url": urls[index]})
                for index in range(1, size + 1)
            ]

        # The first half is a line ending in a two-URL cycle. Each URL in the
        # second half adds one hop before its counterpart in that line.
        expected = []
        for index in range(1, size + 1):
            extra_hop, tail_offset = divmod(index - 1, half)
            hops = max(2, half - tail_offset) + extra_hop
            final_index = half if tail_offset == half - 1 else half - 1
            expected.append(
                AffectedUrl(
                    url_id=nodes[index].id, detail={"hops": hops, "final_url": urls[final_index]}
                )
            )
        return expected

    def measure_sql() -> tuple[int, list[AffectedUrl]]:
        ticks = 0

        def count() -> int:
            nonlocal ticks
            ticks += 1
            return 0

        with closing(connect(file, read_only=True)) as connection:
            (sql,) = connection.execute(
                "SELECT reproduce_sql FROM rules WHERE id = 'redirect-chain'"
            ).fetchone()
            assert sql == REDIRECT_CHAIN.reproduce_sql
            connection.set_progress_handler(count, 100)
            rows = [
                AffectedUrl(url_id=url_id, detail=json.loads(detail))
                for url_id, detail in connection.execute(sql)
            ]
        return ticks, sorted(rows, key=lambda row: row.url_id)

    assert query(file, "SELECT state FROM crawl") == [("running",)]
    expected_small = record_graph(128, 0, more)
    small, small_rows = measure_sql()
    expected_large = expected_small + record_graph(256, 1, None)
    large, large_rows = measure_sql()

    ids = dict(query(file, "SELECT url, id FROM urls"))
    details = {row.url_id: row.detail for row in large_rows}
    for url, (hops, final_url) in examples.items():
        assert details[ids[url]] == {"hops": hops, "final_url": final_url}

    assert small_rows == expected_small
    assert large_rows == expected_large
    assert read_affected_urls(file, "redirect-chain", (REDIRECT_CHAIN,)) == expected_large
    # The second measurement includes both components. Allow 50% over linear growth
    # for differences in SQLite's query plans.
    assert large < 4.5 * small, (small, large)
