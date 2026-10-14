"""Issues of a Crawl, as the documented tables hold them (040-add-rules, rules; seam 3+6)."""

import json
from pathlib import Path
from typing import Any

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
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
