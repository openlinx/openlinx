"""Rule configuration fixed per Crawl (040-add-rules D6, D10, D14; seam 3+6)."""

import json
from pathlib import Path
from typing import Any

from spider.rules.registry import RULES
from spider.store.issues import (
    INTERNAL_PAGES,
    health,
    health_affected_in,
    read_affected_urls,
    read_issues,
)
from spider.store.reading import reading
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site({"/": Page(body="<title>Home</title>")})
# A 61-character title: over the default max_chars of 60, under 100.
LONG_TITLE = Site(
    {"/": Page(body="<title>Buy running shoes, trail boots and sandals online at low cost</title>")}
)


def test_crawl_records_the_thresholds_it_used(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")

    [(thresholds,)] = query(
        crawled(server.url("/")), "SELECT thresholds FROM rules WHERE id = 'title-too-long'"
    )

    assert json.loads(thresholds) == {"max_chars": 70}


def read_back(crawl_file: Path) -> tuple[Any, ...]:
    """What a reader of the Crawl sees: its Issues, title-too-long's Affected URLs, its Health
    Score through the reader and on the crawl row."""
    with reading(crawl_file) as connection:
        score = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))
    return (
        read_issues(crawl_file, RULES),
        read_affected_urls(crawl_file, "title-too-long", RULES),
        score,
        query(crawl_file, "SELECT health_score, health_affected_page_count FROM crawl"),
    )


def test_later_edits_do_not_change_a_completed_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(LONG_TITLE).url("/"))
    completed = read_back(crawl_file)

    (temp_workspace.root / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 100\n")

    issues, too_long, _, _ = completed
    assert ("title-too-long" in [issue.rule_id for issue in issues], len(too_long)) == (True, 1)
    assert read_back(crawl_file) == completed
