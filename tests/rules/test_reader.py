"""The Issues reader's two paths (040-add-rules D16; seam 2)."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update

from spider.aio import loop_factory
from spider.rules.registry import RULES
from spider.store.crawls import record_state
from spider.store.issues import materialise_issues, read_affected_urls, read_issues
from spider.store.schema import pages
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
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
        asyncio.run(materialise_issues(writer, RULES), loop_factory=loop_factory)
        writer.run(record_state("stopped", AT, "max_urls"))
        writer.run(executing(TITLED))
        writer.flush()
        # Stopped after its pass: affected_urls holds the Issues, though the Page changed since.
        stopped = issues_of(crawl_file)
        writer.run(record_state("running", AT))
        writer.run(record_state("failed", AT, "site_unreachable"))
        writer.flush()
        failed = issues_of(crawl_file)

    assert (stopped, failed) == (([("title-missing", 1)], [url_id]), ([], []))
