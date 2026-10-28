"""The row writer of spider.store.pages (030-add-page-data D1; seam 2)."""

from dataclasses import fields
from datetime import UTC, datetime

from spider.crawl.urls import parse_seed
from spider.store.page_records import CookieRow, PageRow
from spider.store.pages import write_cookies, write_pages
from spider.store.records import FetchedUrl, Provenance
from spider.store.rows import HandlerRows
from spider.store.schema import cookies, pages
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
        page = PageRow(
            url_id=url_id,
            address="https://bücher.test/über",
            url_encoded_address=url,
            url_path="/über",
            url_query=None,
            content_type="text/html",
            status_code=200,
            response_time_ms=12,
            last_modified=None,
            set_cookie_count=1,
            crawl_timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        )
        cookie = CookieRow(
            url_id=url_id,
            ordinal=1,
            name="sid",
            domain=None,
            path="/",
            expires=datetime(2027, 1, 2, tzinfo=UTC),
            max_age=None,
            secure=True,
            http_only=False,
            partitioned=False,
            same_site="lax",
        )
        fetched = FetchedUrl(
            url_id=url_id,
            provenance=Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None),
            status_code=200,
            content_type="text/html",
            fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            response_time_ms=12,
            parsed=True,
            rows=(HandlerRows(write_pages, (page,)), HandlerRows(write_cookies, (cookie,))),
        )
        writer.run(record_fetched(fetched))
        replay_now(writer)

    assert (
        query(crawl.path, "SELECT url_id, address, url_encoded_address FROM pages"),
        query(crawl.path, "SELECT url_id, ordinal, name, expires, secure FROM cookies"),
    ) == (
        [(url_id, "https://bücher.test/über", url)],
        [(url_id, 1, "sid", "2027-01-02T00:00:00.000Z", 1)],
    )


def test_the_cookie_row_has_every_cookies_column_in_order() -> None:
    assert [field.name for field in fields(CookieRow)] == [column.name for column in cookies.c]


def test_the_page_row_has_every_pages_column_in_order() -> None:
    assert [*(field.name for field in fields(PageRow)), "crawl_depth"] == [
        column.name for column in pages.c
    ]
