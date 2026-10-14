"""The units of spider.store.crawls that a Crawl runs (020-add-crawl-core D10, D14; seam 2)."""

from datetime import UTC, datetime

import pytest

from spider.store.crawls import crawl_summary, record_state
from spider.store.records import CrawlSummary
from spider.store.transitions import CrawlStateError
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_row, create_any_crawl
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
