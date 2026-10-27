"""The response_headers writer (022-add-fetch-policy D7; seam 2)."""

from datetime import UTC, datetime

from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchedUrl, Provenance, ResponseHeaders
from spider.store.response_headers import write_response_headers
from spider.store.rows import HandlerRows
from spider.store.urls import record_fetched, record_seed
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
        seed_id = writer.run(
            record_seed(NormalizedUrl("https://example.com/"), is_internal=True, in_scope=True)
        )
        # As the engine records a fetched URL: its handler rows go in the URL's own unit.
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=seed_id,
                    provenance=Provenance(
                        crawl_depth=0, discovered_via="seed", found_on_url_id=None
                    ),
                    status_code=200,
                    content_type="text/html; charset=utf-8",
                    fetched_at=datetime(2026, 10, 28, 9, 30, tzinfo=UTC),
                    response_time_ms=140,
                    parsed=True,
                    attempt_count=1,
                    redirect=None,
                    discovered=(),
                    rows=(
                        HandlerRows(
                            write_response_headers,
                            (ResponseHeaders(url_id=seed_id, headers=headers),),
                        ),
                    ),
                )
            )
        )
        replay_now(writer)

    assert query(crawl.path, "SELECT url_id, headers FROM response_headers") == [
        (
            seed_id,
            '[["Content-Type","text/html; charset=utf-8"],'
            '["Set-Cookie","sid=***; Path=/"],["Set-Cookie","theme=***"]]',
        )
    ]
