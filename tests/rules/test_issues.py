"""Issues of a Crawl, as the documented tables hold them (040-add-rules, rules; seam 3+6)."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from spider.rules.registry import RULES
from spider.store.issues import (
    INTERNAL_PAGES,
    IssueReader,
    LiveIssues,
    StoredIssues,
    health,
    read_affected_urls,
    read_issues,
)
from spider.store.reading import reading
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.fixture_site.server import ServerHandle
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


@contextmanager
def running_crawl(
    temp_workspace: TempWorkspace, server: ServerHandle, recorded: str
) -> Iterator[Path]:
    """The crawl file of a Crawl of `server` that is still running, once the Page at `recorded`
    is written: one request at a time, so /slow is requested only after it."""
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
                    (server.url(recorded),),
                )
                or None
            )
        )
        yield crawl_file
    finally:
        crawl.join()


@pytest.mark.slow
def test_issue_visible_before_the_crawl_ends(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SLOW_SITE)
    with running_crawl(temp_workspace, server, "/notitle") as crawl_file:
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

    assert (state, issues, affected) == (
        [("running",)],
        [("title-missing", 1)],
        [server.url("/notitle")],
    )


@pytest.mark.slow
def test_score_before_the_passes(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # The untitled /notitle is recorded, so a score kept while the Crawl runs would show.
    with running_crawl(temp_workspace, fixture_site(SLOW_SITE), "/notitle") as crawl_file:
        running = query(
            crawl_file,
            "SELECT state, health_score, health_internal_page_count, "
            "health_affected_page_count, health_calculated_at FROM crawl",
        )

    assert running == [("running", None, None, None, None)]


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
    with running_crawl(temp_workspace, fixture_site(SLOW_TWINS), "/twin") as crawl_file:
        state = query(crawl_file, "SELECT state FROM crawl")
        stored = query(crawl_file, "SELECT count(*) FROM affected_urls")
        issues = [
            (issue.rule_id, issue.affected_count)
            for issue in read_issues(crawl_file, RULES)
            if issue.rule_id == "title-duplicate"
        ]

    assert (state, stored, issues) == ([("running",)], [(0,)], [("title-duplicate", 2)])


def test_live_and_materialised_issues_agree(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(RULE_PAGES).url("/rules/"))
    enabled = [
        rule_id for (rule_id,) in query(crawl_file, "SELECT id FROM rules WHERE enabled = 1")
    ]
    with reading(crawl_file) as connection:
        live, stored = (
            read_through(connection, adapter(connection, RULES), enabled)
            for adapter in (LiveIssues, StoredIssues)
        )

    # Every Rule fires on RULE_PAGES, so the comparison is not vacuous.
    assert (live, sorted(rule_id for rule_id, *_ in stored[0])) == (
        stored,
        sorted(FIRING_ON_RULE_PAGES),
    )


def read_through(connection: Any, reader: IssueReader, rule_ids: list[str]) -> tuple[Any, ...]:
    """What a reader gives: the Issues, each Rule's Affected URLs and those the Health Score
    scores, each in a fixed order."""
    return (
        sorted(tuple(row) for row in connection.execute(reader.issues())),
        {
            rule_id: sorted(connection.execute(reader.affected_urls(rule_id)))
            for rule_id in rule_ids
        },
        health(connection, INTERNAL_PAGES, reader.health_affected()),
    )


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
