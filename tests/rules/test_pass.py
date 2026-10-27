"""The units of the Issues pass (040-add-rules D5, D15; seam 2)."""

import asyncio
from dataclasses import replace

from spider.aio import loop_factory
from spider.rules.passes import materialise_issues
from spider.rules.registry import RULES
from spider.rules.titles import TITLE_MISSING
from spider.services.hooks import default_hooks
from spider.store.issue_units import affected_urls_unit
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import query
from tests.support.page_data import page_data
from tests.support.rules import SHOES, crawl_with_page, crawl_with_pages
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_the_issues_pass_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, **page_data("<h1>Sale</h1><p>Everything half price this week.</p>")
    )

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        for _ in range(2):
            asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)
        replay_now(writer)

    assert query(
        crawl_file, "SELECT rule_id, url_id, detail FROM affected_urls WHERE rule_id LIKE 'title-%'"
    ) == [("title-missing", url_id, None)]
    assert query(
        crawl_file,
        "SELECT health_score, health_internal_page_count, health_affected_page_count FROM crawl",
    ) == [(0, 1, 1)]


def test_the_issues_pass_comes_last() -> None:
    assert [crawl_pass.name for crawl_pass in default_hooks().passes][-1:] == ["issues"]


def test_a_rule_query_ending_in_a_comment_is_run_as_written(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    commented = replace(
        TITLE_MISSING, reproduce_sql=TITLE_MISSING.reproduce_sql + "\n-- A comment ends it."
    )

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        writer.run(affected_urls_unit(commented))

    assert query(crawl_file, "SELECT rule_id, url_id FROM affected_urls") == [
        ("title-missing", url_id)
    ]


def test_a_rule_query_with_a_colon_is_run_as_written(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    colon = replace(
        TITLE_MISSING, reproduce_sql=TITLE_MISSING.reproduce_sql + "\n-- Widths come :later."
    )

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        writer.run(affected_urls_unit(colon))

    assert query(crawl_file, "SELECT rule_id, url_id FROM affected_urls") == [
        ("title-missing", url_id)
    ]


def test_a_second_pass_does_not_duplicate_rows(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(temp_workspace, SHOES, SHOES)

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        for _ in range(2):
            asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)

    assert query(
        crawl_file, "SELECT count(*) FROM affected_urls WHERE rule_id = 'title-duplicate'"
    ) == [(2,)]
