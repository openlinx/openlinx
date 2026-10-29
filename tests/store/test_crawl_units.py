"""The units of spider.store.crawls that a Crawl runs (020-add-crawl-core D10, D14; seam 2)."""

import json
from datetime import UTC, datetime

import pytest

from spider.store.crawls import crawl_summary, record_continue, record_state, record_warnings
from spider.store.records import CrawlSummary
from spider.store.transitions import CrawlStateError
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawling import stopped_with_an_error
from tests.support.crawls import crawl_row, create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_crawls_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(record_state("completed", datetime(2026, 9, 27, 15, 0, tzinfo=UTC)))
        summary = writer.run(crawl_summary())
        replay_now(writer)

    assert (summary, crawl_row(crawl.path)["completed_at"]) == (
        CrawlSummary(
            state="completed",
            stop_reason=None,
            crawl_mode="spider",
            section_crawl=False,
            started_at="2026-09-27T14:03:12.345Z",
            seed="https://example.com/",
            seed_count=1,
        ),
        "2026-09-27T15:00:00.000Z",
    )


def test_the_state_is_checked_against_the_state_the_unit_reads(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)
    at = datetime(2026, 9, 27, 15, 0, tzinfo=UTC)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(record_state("completed", at))
        with pytest.raises(CrawlStateError):
            writer.run(record_state("completed", at))

    assert crawl_row(crawl.path)["state"] == "completed"


def test_the_units_of_a_continue_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl_file = stopped_with_an_error()
    config = json.loads(crawl_row(crawl_file)["config"])
    config["crawl"]["rate"] = 2.0
    warning = {"level": "warning", "code": "possible_blocking", "message": "M", "hint": None}

    with CrawlWriter(crawl_file, FakeClock()) as writer:
        writer.run(record_continue(config, datetime(2026, 9, 27, 15, 0, tzinfo=UTC)))
        writer.run(record_warnings([{**warning, "details": {"host": "site.test"}}]))
        replay_now(writer)

    row = crawl_row(crawl_file)
    assert (
        row["state"],
        row["stop_reason"],
        json.loads(row["config"])["crawl"]["rate"],
        json.loads(row["warnings"]),
        dict(query(crawl_file, "SELECT url, fetch_state FROM urls")),
    ) == (
        "running",
        None,
        2.0,
        [{**warning, "details": {"host": "site.test"}}],
        {
            "http://site.test/": "fetched",
            "http://site.test/a": "queued",
            "http://site.test/b": "queued",
        },
    )
