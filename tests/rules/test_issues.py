"""Issues of a Crawl, as the documented tables hold them (040-add-rules, rules; seam 3+6)."""

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from spider.rules.registry import RULES
from spider.store.issues import read_affected_urls, read_issues
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

TWO_UNTITLED_PAGES = Site(
    {
        "/": Page(body='<p>No title here. <a href="/second">Second</a></p>'),
        "/second": Page(body="<p>No title here either.</p>"),
    }
)

# The fixture pages under /rules/: each later Rule's slice adds the pages its Rule fires on.
RULE_PAGES = Site(
    {
        "/rules/": Page(body='<title>Rules</title><a href="/rules/untitled">Untitled</a>'),
        "/rules/untitled": Page(body="<p>No title here.</p>"),
    }
)


def test_issue_row_counts_its_affected_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(TWO_UNTITLED_PAGES).url("/"))

    assert query(
        crawl_file,
        "SELECT category, issue_type, priority, affected_count FROM issues "
        "WHERE rule_id = 'title-missing'",
    ) == [("titles", "issue", "high", 2)]


def affected_urls_by_rule(crawl_file: Path, sql: str) -> dict[str, list[tuple[int, Any]]]:
    found: dict[str, list[tuple[int, Any]]] = {}
    for rule_id, url_id, detail in query(crawl_file, sql):
        found.setdefault(rule_id, []).append(
            (url_id, None if detail is None else json.loads(detail))
        )
    return {rule_id: sorted(rows) for rule_id, rows in found.items()}


def test_a_rule_s_query_returns_its_stored_affected_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(RULE_PAGES).url("/rules/"))
    returned: dict[str, list[tuple[int, Any]]] = {}
    for rule_id, sql in query(crawl_file, "SELECT id, reproduce_sql FROM rules WHERE enabled = 1"):
        rows = [
            (url_id, None if detail is None else json.loads(detail))
            for url_id, detail in query(crawl_file, sql)
        ]
        if rows:
            returned[rule_id] = sorted(rows)
    stored = affected_urls_by_rule(crawl_file, "SELECT rule_id, url_id, detail FROM affected_urls")

    # title-missing fires on /rules/untitled, so the comparison is not vacuous.
    assert (returned, "title-missing" in stored) == (stored, True)


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
        issues = [(issue.rule_id, issue.affected_count) for issue in read_issues(crawl_file, RULES)]
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
