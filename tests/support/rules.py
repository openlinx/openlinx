"""Crawl files that hold the rows a Rule reads, for seam-2 tests (040-add-rules, Test seams)."""

from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spider.crawl.urls import NormalizedUrl
from spider.rules.settings import RulesSettings
from spider.services.rules import rule_rows
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.records import FetchedUrl, ParseError
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace

PAGE_URL = NormalizedUrl("https://site.test/")


def crawl_with_page(
    temp_workspace: TempWorkspace,
    *,
    disabled: Collection[str] = (),
    parse_error: ParseError | None = None,
    **page_data: Any,
) -> tuple[Path, int]:
    """A crawl file and the URL id of its one analysed Page, with these Page data columns,
    whose rules table marks the Rules named in `disabled` off; `extractor_error` as
    `parse_error` makes it a Page on which an extractor failed.

    The rows go through the store's own units, as a Crawl writes them: the Seed, then its
    HTML response with its Page row.
    """
    recorded = rule_rows(RulesSettings().model_dump(by_alias=True))
    rules = tuple(replace(rule, enabled=rule.id not in disabled) for rule in recorded)
    crawl = create_any_crawl(temp_workspace, rules=rules)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(PAGE_URL, is_internal=True, in_scope=True))
        page = PageRow(url_id=url_id, address=PAGE_URL, url_encoded_address=PAGE_URL, **page_data)
        fetched = FetchedUrl(
            url_id=url_id,
            status_code=200,
            content_type="text/html",
            fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            response_time_ms=1,
            parsed=True,
            parse_error=parse_error,
            rows=(page,),
        )
        writer.run(record_fetched(fetched, {PageRow: write_page}))
    return crawl.path, url_id
