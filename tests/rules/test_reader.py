"""The Issues reader's two paths (040-add-rules D16; seam 2)."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import update

from spider.aio import loop_factory
from spider.output.diagnostics import SpiderError
from spider.rules.registry import RULES
from spider.rules.titles import TITLE_MISSING
from spider.store.crawls import record_state
from spider.store.issues import (
    affected_urls_in,
    issues_in,
    materialise_issues,
    read_affected_urls,
    read_issues,
    read_url_issues,
    stored_affected_urls,
)
from spider.store.reading import reading
from spider.store.records import AffectedUrl, UrlIssue
from spider.store.schema import pages
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import default_rule_rows, query
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
# What a later run that records the Page again with a title would leave in its row.
TITLED = update(pages).values(title_count=1, title_1="Shoes", title_1_length=5)


def issues_of(crawl_file: Path) -> tuple[list[tuple[str, int]], list[int]]:
    return (
        [(issue.rule_id, issue.affected_count) for issue in read_issues(crawl_file, RULES)],
        [url.url_id for url in read_affected_urls(crawl_file, "title-missing", RULES)],
    )


def test_a_crawl_without_a_final_pass_is_read_live(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)
        writer.run(record_state("stopped", AT, "max_urls"))
        writer.run(executing(TITLED))
        writer.flush()
        # Stopped after its pass: affected_urls holds the Issues, though the Page changed since.
        stopped = issues_of(crawl_file)
        writer.run(record_state("running", AT))
        writer.run(record_state("failed", AT, "site_unreachable"))
        writer.flush()
        failed = issues_of(crawl_file)

    assert (stopped, failed, query(crawl_file, "SELECT rule_id, url_id FROM affected_urls")) == (
        ([("title-missing", 1)], [url_id]),
        ([], []),
        [("title-missing", url_id)],
    )


def test_a_disabled_rule_has_no_affected_urls_read_live(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, disabled={"title-missing"}, title_count=0)

    assert read_affected_urls(crawl_file, "title-missing", RULES) == []


def test_an_unknown_rule_id_is_rule_not_found(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, title_count=0)

    with pytest.raises(SpiderError) as raised:
        read_affected_urls(crawl_file, "nope", RULES)

    assert raised.value.code == "rule_not_found"


def test_issues_of_a_rule_the_catalogue_lacks_come_after_its_own(
    temp_workspace: TempWorkspace,
) -> None:
    # A Rule of a later tool, recorded and stored by it, which this catalogue does not have.
    later = replace(TITLE_MISSING, id="a-later-rule")
    (missing,) = [row for row in default_rule_rows() if row.id == TITLE_MISSING.id]
    recorded = replace(missing, id=later.id)
    crawl_file, _ = crawl_with_page(temp_workspace, more_rules=(recorded,), title_count=0)
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(
            materialise_issues(writer, (*RULES, later), FakeClock()), loop_factory=loop_factory
        )
        writer.run(record_state("completed", AT))

    assert [issue.rule_id for issue in read_issues(crawl_file, RULES)] == [
        "title-missing",
        "a-later-rule",
    ]


def test_the_affected_urls_of_a_rule_the_catalogue_lacks_are_read_as_stored(
    temp_workspace: TempWorkspace,
) -> None:
    later = replace(TITLE_MISSING, id="a-later-rule")
    (missing,) = [row for row in default_rule_rows() if row.id == TITLE_MISSING.id]
    crawl_file, url_id = crawl_with_page(
        temp_workspace, more_rules=(replace(missing, id=later.id),), title_count=0
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(
            materialise_issues(writer, (*RULES, later), FakeClock()), loop_factory=loop_factory
        )
        writer.run(record_state("completed", AT))

    assert read_affected_urls(crawl_file, "a-later-rule", RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_the_issues_of_one_url_are_read_live(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    disabled, disabled_id = crawl_with_page(
        temp_workspace, disabled={"title-missing"}, title_count=0
    )

    assert (
        read_url_issues(crawl_file, url_id, RULES),
        read_url_issues(disabled, disabled_id, RULES),
    ) == ([UrlIssue(rule_id="title-missing", url_id=url_id, detail=None)], [])


def test_the_issues_of_one_url_are_read_as_stored(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)
        # The Page changes after the pass, so only the stored rows still list title-missing.
        writer.run(executing(TITLED))
        writer.run(record_state("completed", AT))

    assert read_url_issues(crawl_file, url_id, RULES) == [
        UrlIssue(rule_id="title-missing", url_id=url_id, detail=None)
    ]


def test_an_issue_and_its_affected_urls_are_read_from_one_snapshot(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)
    with CrawlWriter(crawl_file, FakeClock()) as writer, reading(crawl_file) as connection:
        issues = [
            (row.rule_id, row.affected_count)
            for row in connection.execute(issues_in(connection, RULES))
        ]
        # Committed between the two reads, while the read is open.
        writer.run(executing(TITLED))
        writer.flush()
        affected = [
            row.url_id
            for row in connection.execute(affected_urls_in(connection, "title-missing", RULES))
        ]

    assert (issues, affected) == ([("title-missing", 1)], [url_id])


def later_rule_crawl(temp_workspace: TempWorkspace) -> Path:
    """A running Crawl whose rules table records a-later-rule, which RULES lacks."""
    (missing,) = [row for row in default_rule_rows() if row.id == TITLE_MISSING.id]
    crawl_file, _ = crawl_with_page(
        temp_workspace, more_rules=(replace(missing, id="a-later-rule"),), title_count=0
    )
    return crawl_file


def test_an_unknown_rule_id_gets_the_closest_ids_the_crawl_records(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_file = later_rule_crawl(temp_workspace)
    with pytest.raises(SpiderError) as live:
        read_affected_urls(crawl_file, "a-later-rul", RULES)
    with pytest.raises(SpiderError) as stored:
        stored_affected_urls(crawl_file, "a-later-rul")

    assert (
        live.value.diagnostic.details["suggestions"],
        stored.value.diagnostic.details["suggestions"],
    ) == (["a-later-rule"], ["a-later-rule"])


def test_a_rule_this_tool_lacks_is_not_read_live(temp_workspace: TempWorkspace) -> None:
    crawl_file = later_rule_crawl(temp_workspace)

    with pytest.raises(SpiderError) as raised:
        read_affected_urls(crawl_file, "a-later-rule", RULES)

    assert (raised.value.code, raised.value.diagnostic.message, raised.value.diagnostic.hint) == (
        "rule_not_found",
        "This version of spider cannot compute the Rule a-later-rule live: another version "
        "made this Crawl.",
        "Run the Rule's reproduce_sql, in the Crawl's rules table, with spider sql.",
    )
