"""Crawl files that hold the rows a Rule reads, for seam-2 tests (040-add-rules, Test seams)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spider.crawl.urls import NormalizedUrl
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.records import FetchedUrl
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace

PAGE_URL = NormalizedUrl("https://site.test/")


def crawl_with_page(temp_workspace: TempWorkspace, **page_data: Any) -> tuple[Path, int]:
    """A crawl file and the URL id of its one analysed Page, with these Page data columns.

    The rows go through the store's own units, as a Crawl writes them: the Seed, then its
    HTML response with its Page row.
    """
    crawl = create_any_crawl(temp_workspace)
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
            rows=(page,),
        )
        writer.run(record_fetched(fetched, {PageRow: write_page}))
    return crawl.path, url_id
