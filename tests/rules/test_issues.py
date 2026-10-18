"""Issues of a Crawl, as the documented tables hold them (040-add-rules, rules; seam 3+6)."""

import json
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from spider.rules.registry import RULES
from spider.store.issues import (
    live_affected_urls,
    live_issues,
    read_affected_urls,
    read_issues,
    stored_affected_urls,
    stored_issues,
)
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

TWO_UNTITLED_PAGES = Site(
    {
        "/": Page(body='<p>No title here. <a href="/second">Second</a></p>'),
        "/second": Page(body="<p>No title here either.</p>"),
    }
)

# The fixture pages under /rules/: each Rule fires on one of them, so a new Rule adds its own.
RULE_PAGES = Site(
    {
        "/rules/": Page(
            body='<title>Rules</title><a href="/rules/untitled">Untitled</a> '
            '<a href="/rules/gone">Gone</a> <a href="/rules/down">Down</a> '
            '<a href="/rules/reset">Reset</a> <a href="/rules/long-title">Long</a> '
            '<a href="/rules/twin-a">Twin</a> <a href="/rules/twin-b">Twin</a> '
            '<a href="/rules/private">Private</a>'
        ),
        "/robots.txt": Robots("User-agent: *\nDisallow: /rules/private\n"),
        "/rules/untitled": Page(body="<p>No title here.</p>"),
        "/rules/gone": Status(404, body="Gone", content_type="text/plain"),
        "/rules/down": Status(503, body="Down", content_type="text/plain"),
        "/rules/reset": Page(body="<p>" + "x" * 100_000 + "</p>", reset_after=100),
        "/rules/long-title": Page(
            body="<title>Buy running shoes, trail boots and sandals online at low cost</title>"
        ),
        "/rules/twin-a": Page(body="<title>Twins</title>"),
        "/rules/twin-b": Page(body="<title>Twins</title>"),
        "/rules/private": Page(body="<title>Private</title>"),
    }
)
# Every Rule: a Rule without a fixture page that it fires on fails the comparisons below.
FIRING_ON_RULE_PAGES = [rule.id for rule in RULES]


def test_issue_row_counts_its_affected_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(TWO_UNTITLED_PAGES).url("/"))

    assert query(
        crawl_file,
        "SELECT category, issue_type, priority, affected_count FROM issues "
        "WHERE rule_id = 'title-missing'",
    ) == [("titles", "issue", "high", 2)]


def decoded(rows: list[tuple[Any, ...]]) -> list[tuple[int, Any]]:
    return sorted(
        (url_id, None if detail is None else json.loads(detail)) for url_id, detail in rows
    )


def test_a_rule_s_query_returns_its_stored_affected_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(RULE_PAGES).url("/rules/"))
    returned = {
        rule_id: rows
        for rule_id, sql in query(
            crawl_file, "SELECT id, reproduce_sql FROM rules WHERE enabled = 1"
        )
        if (rows := decoded(query(crawl_file, sql)))
    }
    stored = {
        rule_id: decoded(
            query(
                crawl_file, "SELECT url_id, detail FROM affected_urls WHERE rule_id = ?", (rule_id,)
            )
        )
        for (rule_id,) in query(crawl_file, "SELECT DISTINCT rule_id FROM affected_urls")
    }

    # Every Rule fires on RULE_PAGES, so the comparison is not vacuous.
    assert (returned, sorted(stored)) == (stored, sorted(FIRING_ON_RULE_PAGES))


def test_detail_is_stored_as_json(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(RULE_PAGES)
    crawl_file = crawled(server.url("/rules/"))
    rows = query(
        crawl_file,
        "SELECT a.detail FROM affected_urls AS a JOIN urls AS u ON u.id = a.url_id "
        "WHERE a.rule_id = 'title-too-long' AND u.url = ?",
        (server.url("/rules/long-title"),),
    )

    assert [json.loads(detail) for (detail,) in rows] == [{"length": 61}]


TWO_SHOES = Site(
    {
        "/": Page(body='<title>Shoes</title><a href="/twin">Twin</a>'),
        "/twin": Page(body="<title>Shoes</title>"),
    }
)


def test_rule_that_did_not_fire_has_no_issue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    at_the_limit = Site({"/": Page(body=f"<title>{'x' * 60}</title>")})
    crawl_file = crawled(fixture_site(at_the_limit).url("/"))

    assert query(crawl_file, "SELECT rule_id FROM issues WHERE rule_id = 'title-too-long'") == []


def test_duplicates_found_by_the_post_crawl_passes(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(TWO_SHOES).url("/"))

    assert query(
        crawl_file, "SELECT count(*) FROM affected_urls WHERE rule_id = 'title-duplicate'"
    ) == [(2,)]


SLOW_SITE = Site(
    {
        "/": Page(body='<title>Home</title><a href="/notitle">a</a> <a href="/slow">b</a>'),
        "/notitle": Page(body="<p>No title here.</p>"),
        "/slow": Page(body="<title>Slow</title>", delay=5.0),
    }
)


def waited_for[T](found: Callable[[], T | None], seconds: float = 4.0) -> T:
    """What `found` returns once it is not None; the Crawl writes on its own thread."""
    deadline = time.monotonic() + seconds
    while (value := found()) is None:
        if time.monotonic() > deadline:
            raise AssertionError(f"Nothing found within {seconds} s.")
        time.sleep(0.05)
    return value


@pytest.mark.slow
def test_issue_visible_before_the_crawl_ends(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_SITE)
    # One request at a time: /slow is requested only after /notitle was recorded.
    crawl = threading.Thread(
        target=crawl_result, args=(server.url("/"),), kwargs={"concurrency": 1}
    )
    crawl.start()
    try:
        waited_for(lambda: True if any(r.path == "/slow" for r in server.requests) else None)
        crawl_file = waited_for(lambda: next(temp_workspace.home.rglob("*.sqlite"), None))
        waited_for(
            lambda: (
                query(
                    crawl_file,
                    "SELECT 1 FROM pages JOIN urls ON urls.id = pages.url_id WHERE urls.url = ?",
                    (server.url("/notitle"),),
                )
                or None
            )
        )
        state = query(crawl_file, "SELECT state FROM crawl")
        issues = [
            (issue.rule_id, issue.affected_count)
            for issue in read_issues(crawl_file, RULES)
            if issue.rule_id == "title-missing"
        ]
        affected = [
            query(crawl_file, "SELECT url FROM urls WHERE id = ?", (url.url_id,))[0][0]
            for url in read_affected_urls(crawl_file, "title-missing", RULES)
        ]
    finally:
        crawl.join()

    assert (state, issues, affected) == (
        [("running",)],
        [("title-missing", 1)],
        [server.url("/notitle")],
    )


SLOW_TWINS = Site(
    {
        "/": Page(body='<title>Shoes</title><a href="/twin">a</a> <a href="/slow">b</a>'),
        "/twin": Page(body="<title>Shoes</title>"),
        "/slow": Page(body="<title>Slow</title>", delay=5.0),
    }
)


@pytest.mark.slow
def test_a_running_crawl_writes_no_affected_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_TWINS)
    # One request at a time: /slow is requested only after /twin was recorded.
    crawl = threading.Thread(
        target=crawl_result, args=(server.url("/"),), kwargs={"concurrency": 1}
    )
    crawl.start()
    try:
        waited_for(lambda: True if any(r.path == "/slow" for r in server.requests) else None)
        crawl_file = waited_for(lambda: next(temp_workspace.home.rglob("*.sqlite"), None))
        waited_for(
            lambda: (
                query(
                    crawl_file,
                    "SELECT 1 FROM pages JOIN urls ON urls.id = pages.url_id WHERE urls.url = ?",
                    (server.url("/twin"),),
                )
                or None
            )
        )
        state = query(crawl_file, "SELECT state FROM crawl")
        stored = query(crawl_file, "SELECT count(*) FROM affected_urls")
        issues = [
            (issue.rule_id, issue.affected_count)
            for issue in read_issues(crawl_file, RULES)
            if issue.rule_id == "title-duplicate"
        ]
    finally:
        crawl.join()

    assert (state, stored, issues) == ([("running",)], [(0,)], [("title-duplicate", 2)])


def test_live_and_materialised_issues_agree(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(RULE_PAGES).url("/rules/"))
    enabled = [
        rule_id for (rule_id,) in query(crawl_file, "SELECT id FROM rules WHERE enabled = 1")
    ]
    live = {rule_id: live_affected_urls(crawl_file, rule_id, RULES) for rule_id in enabled}
    stored = {rule_id: stored_affected_urls(crawl_file, rule_id) for rule_id in enabled}

    stored_found = stored_issues(crawl_file, RULES)

    # Every Rule fires on RULE_PAGES, so the comparison is not vacuous.
    assert (
        live_issues(crawl_file, RULES),
        live,
        sorted(issue.rule_id for issue in stored_found),
    ) == (stored_found, stored, sorted(FIRING_ON_RULE_PAGES))


def test_disabled_rule_produces_no_issue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    (temp_workspace.root / "spider.toml").write_bytes(b"[rules.title-missing]\nenabled = false\n")

    crawl_file = crawled(fixture_site(TWO_UNTITLED_PAGES).url("/"))

    assert query(crawl_file, "SELECT rule_id FROM issues WHERE rule_id = 'title-missing'") == []


def test_a_crawl_stopped_by_the_url_limit_lists_its_issues_as_stored(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(TWO_UNTITLED_PAGES).url("/"), "--max-urls", "1")

    assert (
        query(crawl_file, "SELECT state FROM crawl"),
        [(issue.rule_id, issue.affected_count) for issue in read_issues(crawl_file, RULES)],
    ) == (
        [("stopped",)],
        [
            ("http-url", 1),
            ("title-missing", 1),
            ("meta-description-missing", 1),
            ("h1-missing", 1),
        ],
    )


def test_client_error_recorded_by_a_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/gone">Gone</a>'),
                "/gone": Status(404, body="Gone", content_type="text/plain"),
            }
        )
    )
    crawl_file = crawled(server.url("/"))

    assert (
        query(crawl_file, "SELECT state FROM crawl"),
        [
            json.loads(detail)
            for (detail,) in query(
                crawl_file,
                "SELECT detail FROM affected_urls JOIN urls ON urls.id = affected_urls.url_id "
                "WHERE affected_urls.rule_id = 'internal-4xx' AND urls.url = ?",
                (server.url("/gone"),),
            )
        ],
    ) == ([("completed",)], [{"status_code": 404}])
