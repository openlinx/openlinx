"""The Health Score of a crawl file's Pages (040-add-rules D8; seam 2)."""

import asyncio
from dataclasses import fields, replace
from typing import Any

from sqlalchemy import select

from spider.aio import loop_factory
from spider.rules.registry import RULES
from spider.rules.titles import TITLE_MISSING
from spider.store.crawls import record_state
from spider.store.issues import (
    INTERNAL_PAGES,
    STORED_AFFECTED_URLS,
    health,
    health_affected_in,
    materialise_issues,
)
from spider.store.reading import reading
from spider.store.records import Health
from spider.store.schema import crawl, pages
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import default_rule_rows
from tests.support.page_data import page_row
from tests.support.rules import TITLE_MULTIPLE, crawl_with_page, crawl_with_pages, recorded
from tests.support.workspace import TempWorkspace


def test_warnings_do_not_lower_the_score(temp_workspace: TempWorkspace) -> None:
    # Over plain HTTP, both Pages are Affected URLs of http-url, a Warning, and of no Issue.
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {"title_count": 1, "title_1": "Shoes", "title_1_length": 5},
        {"title_count": 1, "title_1": "Boots", "title_1_length": 5},
        base="http://site.test/",
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)

    assert found == Health(score=100, internal_pages=2, affected_pages=0)


def test_a_page_with_several_issues_counts_once(temp_workspace: TempWorkspace) -> None:
    # A Rule of a later tool, of Issue Type issue, that fires on the same untitled Page.
    later = replace(TITLE_MISSING, id="a-later-rule")
    (missing,) = [row for row in default_rule_rows() if row.id == TITLE_MISSING.id]
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {"title_count": 0},
        {"title_count": 1, "title_1": "Shoes", "title_1_length": 5},
        {"title_count": 1, "title_1": "Boots", "title_1_length": 5},
        {"title_count": 1, "title_1": "Socks", "title_1_length": 5},
        more_rules=(replace(missing, id=later.id),),
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(
            materialise_issues(writer, (*RULES, later), FakeClock()), loop_factory=loop_factory
        )

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)

    assert found == Health(score=75, internal_pages=4, affected_pages=1)


def test_health_score_of_a_segment(temp_workspace: TempWorkspace) -> None:
    # The fifth Page, outside the Segment, is untitled too.
    crawl_file, ids = crawl_with_pages(
        temp_workspace,
        {"title_count": 0},
        {"title_count": 1, "title_1": "Shoes", "title_1_length": 5},
        {"title_count": 1, "title_1": "Boots", "title_1_length": 5},
        {"title_count": 1, "title_1": "Socks", "title_1_length": 5},
        {"title_count": 0},
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)
    segment = select(pages.c.url_id).where(pages.c.url_id.in_(ids[:4]))

    with reading(crawl_file) as connection:
        found = health(connection, segment, STORED_AFFECTED_URLS)

    assert found == Health(score=75, internal_pages=4, affected_pages=1)


def test_live_health_score_of_a_running_crawl(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {"title_count": 0},
        {"title_count": 1, "title_1": "Shoes", "title_1_length": 5},
    )

    with reading(crawl_file) as connection:
        state: str = connection.execute(select(crawl.c.state)).scalar_one()
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert (state, found) == ("running", Health(score=50, internal_pages=2, affected_pages=1))


def test_a_disabled_rule_does_not_lower_the_live_score(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, disabled={TITLE_MISSING.id}, title_count=0)

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert found == Health(score=100, internal_pages=1, affected_pages=0)


def page_data(html: str) -> dict[str, Any]:
    """The Page data columns that the built-in extractors give a Page with this HTML."""
    row = page_row(html)
    kept = {field.name for field in fields(row)} - {"url_id", "address", "url_encoded_address"}
    return {name: getattr(row, name) for name in kept}


def test_a_finished_crawl_is_scored_from_its_stored_issues(
    temp_workspace: TempWorkspace,
) -> None:
    # A crawl file of a later tool, whose pass stored title-multiple's Affected URLs.
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        page_data("<title>Running shoes</title><title>Running shoes | Shop</title>"),
        page_data("<title>Trail boots</title>"),
        more_rules=(recorded(TITLE_MULTIPLE),),
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        later = (*RULES, TITLE_MULTIPLE)
        asyncio.run(materialise_issues(writer, later, FakeClock()), loop_factory=loop_factory)
        writer.run(record_state("completed", FakeClock().now()))

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert found == Health(score=50, internal_pages=2, affected_pages=1)
