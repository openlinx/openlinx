"""The row writer of spider.store.pages (030-add-page-data D1; seam 2)."""

from datetime import UTC, datetime

from spider.crawl.urls import parse_seed
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.records import FetchedUrl
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_pages_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    url = parse_seed("https://xn--bcher-kva.test/%C3%BCber")
    assert isinstance(url, str)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(url, is_internal=True, in_scope=True))
        page = PageRow(url_id=url_id, address="https://bücher.test/über", url_encoded_address=url)
        fetched = FetchedUrl(
            url_id=url_id,
            status_code=200,
            content_type="text/html",
            fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            response_time_ms=12,
            parsed=True,
            rows=(page,),
        )
        writer.run(record_fetched(fetched, {PageRow: write_page}))
        replay_now(writer)

    assert query(crawl.path, "SELECT url_id, address, url_encoded_address FROM pages") == [
        (url_id, "https://bücher.test/über", url)
    ]
