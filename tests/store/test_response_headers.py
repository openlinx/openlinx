"""The response_headers writer (022-add-fetch-policy D7; seam 2)."""

from spider.crawl.urls import NormalizedUrl
from spider.store.records import ResponseHeaders
from spider.store.response_headers import write_response_headers
from spider.store.urls import record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_the_response_headers_writer_runs_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    headers = (
        ("Content-Type", "text/html; charset=utf-8"),
        ("Set-Cookie", "sid=***; Path=/"),
        ("Set-Cookie", "theme=***"),
    )

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed = NormalizedUrl("https://example.com/")
        seed_id = writer.run(record_seed(seed, is_internal=True, in_scope=True))
        rows = [ResponseHeaders(url_id=seed_id, headers=headers)]
        writer.run(lambda connection: write_response_headers(connection, rows))
        replay_now(writer)

    assert query(crawl.path, "SELECT url_id, headers FROM response_headers") == [
        (
            seed_id,
            '[["Content-Type","text/html; charset=utf-8"],'
            '["Set-Cookie","sid=***; Path=/"],["Set-Cookie","theme=***"]]',
        )
    ]
