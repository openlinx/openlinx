"""The row writer of spider.store.pages (030-add-page-data D1; seam 2)."""

from spider.crawl.urls import parse_seed
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.urls import record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_units_of_pages_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    url = parse_seed("https://site.test/about")
    assert isinstance(url, str)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(url, is_internal=True, in_scope=True))
        row = PageRow(url_id=url_id, address=url)
        writer.run(lambda connection: write_page(connection, row))
        replay_now(writer)

    assert query(crawl.path, "SELECT url_id, address FROM pages") == [(url_id, url)]
