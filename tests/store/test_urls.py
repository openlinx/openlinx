"""The units of spider.store.urls (020-add-crawl-core D1, D2, D14; seam 2)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, event, text

from spider.crawl.urls import NormalizedUrl, parse_seed
from spider.store.connections import opening
from spider.store.records import (
    DiscoveredVia,
    ErroredUrl,
    FetchedUrl,
    NewUrl,
    QueuedUrl,
    SkippedUrl,
    SkipReason,
    UrlCounts,
)
from spider.store.urls import (
    next_depth,
    queued_batch,
    record_error,
    record_fetched,
    record_seed,
    record_skipped,
    record_unwritten,
    url_counts,
)
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def _url(text: str) -> NormalizedUrl:
    url = parse_seed(text)
    assert isinstance(url, str)
    return url


def _new(
    text: str,
    *,
    crawl_depth: int = 1,
    discovered_via: DiscoveredVia = "hyperlink",
    skip_reason: SkipReason | None = None,
) -> NewUrl:
    return NewUrl(
        url=_url(text),
        crawl_depth=crawl_depth,
        discovered_via=discovered_via,
        is_internal=True,
        in_scope=True,
        skip_reason=skip_reason,
    )


def _fetched(url_id: int, *discovered: NewUrl) -> FetchedUrl:
    return FetchedUrl(
        url_id=url_id,
        status_code=200,
        content_type="text/html",
        fetched_at=datetime(2026, 10, 14, 9, 0, tzinfo=UTC),
        response_time_ms=10,
        parsed=True,
        discovered=discovered,
    )


@dataclass(frozen=True, slots=True)
class Note:
    url_id: int


def _write_note(connection: Connection, row: Note) -> None:
    connection.execute(text("CREATE TABLE IF NOT EXISTS test_notes (url_id INTEGER)"))
    connection.execute(text("INSERT INTO test_notes VALUES (:url_id)"), {"url_id": row.url_id})


def test_the_units_of_urls_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    seed = _url("https://site.test/")
    found = (
        _new("https://site.test/a"),
        _new("https://site.test/b"),
        _new("https://site.test/a"),
        _new("https://site.test/c"),
    )

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(seed, is_internal=True, in_scope=True))
        writer.run(record_seed(seed, is_internal=True, in_scope=True))
        first = writer.run(queued_batch(0, 0, 10))
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=seed_id,
                    status_code=200,
                    content_type="text/html",
                    fetched_at=datetime(2026, 9, 27, 14, 3, 13, tzinfo=UTC),
                    response_time_ms=120,
                    parsed=True,
                    discovered=found,
                    rows=(Note(seed_id),),
                ),
                {Note: _write_note},
            )
        )
        writer.run(record_skipped(SkippedUrl(seed_id + 2, "excluded"), {}))
        deeper = writer.run(next_depth(0))
        second = writer.run(queued_batch(1, 0, 1))
        writer.run(
            record_error(
                ErroredUrl(
                    url_id=seed_id + 1,
                    fetch_error="connection_refused",
                    fetch_error_message="ConnectionRefusedError: refused",
                    fetched_at=datetime(2026, 9, 27, 14, 3, 14, tzinfo=UTC),
                ),
                {},
            )
        )
        writer.run(record_unwritten(seed_id + 3, "ValueError: no row"))
        counts = writer.run(url_counts())
        replay_now(writer)

    assert (
        first,
        deeper,
        second,
        counts,
        query(
            crawl.path,
            "SELECT url, crawl_depth, fetch_state, skip_reason, fetch_error, status_code, "
            "content_type, response_time_ms, fetched_at FROM urls ORDER BY id",
        ),
        query(crawl.path, "SELECT url_id FROM test_notes"),
    ) == (
        (
            QueuedUrl(
                id=seed_id, url=seed, crawl_depth=0, discovered_via="seed", found_on_url_id=None
            ),
        ),
        1,
        (
            QueuedUrl(
                id=seed_id + 1,
                url=_url("https://site.test/a"),
                crawl_depth=1,
                discovered_via="hyperlink",
                found_on_url_id=seed_id,
            ),
        ),
        UrlCounts(
            discovered=4,
            fetched=1,
            errors=2,
            skipped=1,
            queued=0,
            pages=1,
            status_2xx=1,
            status_3xx=0,
            status_4xx=0,
            status_5xx=0,
            status_other=0,
        ),
        [
            (
                "https://site.test/",
                0,
                "fetched",
                None,
                None,
                200,
                "text/html",
                120,
                "2026-09-27T14:03:13.000Z",
            ),
            (
                "https://site.test/a",
                1,
                "error",
                None,
                "connection_refused",
                None,
                None,
                None,
                "2026-09-27T14:03:14.000Z",
            ),
            ("https://site.test/b", 1, "skipped", "excluded", None, None, None, None, None),
            ("https://site.test/c", 1, "error", None, "record_failed", None, None, None, None),
        ],
        [(seed_id,)],
    )


def test_a_followed_link_requeues_a_url_that_only_unfollowed_links_reached(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(
            record_seed(_url("https://site.test/"), is_internal=True, in_scope=True)
        )
        writer.run(
            record_fetched(
                _fetched(
                    seed_id,
                    _new(
                        "https://site.test/amp",
                        discovered_via="amphtml",
                        skip_reason="link_type_not_followed",
                    ),
                    _new("https://site.test/p", skip_reason="nofollow"),
                    _new("https://site.test/q", skip_reason="nofollow"),
                    _new("https://site.test/out"),
                    _new("https://site.test/about"),
                ),
                {},
            )
        )
        writer.run(record_skipped(SkippedUrl(seed_id + 4, "excluded"), {}))
        about_id = seed_id + 5
        writer.run(
            record_fetched(
                _fetched(
                    about_id,
                    _new("https://site.test/amp", crawl_depth=2),
                    _new("https://site.test/p", crawl_depth=2, discovered_via="meta_refresh"),
                    _new("https://site.test/q", crawl_depth=2, skip_reason="nofollow"),
                    _new("https://site.test/out", crawl_depth=2),
                    _new("https://site.test/", crawl_depth=2),
                ),
                {},
            )
        )
        replay_now(writer)

    assert query(
        crawl.path,
        "SELECT url, crawl_depth, discovered_via, found_on_url_id, fetch_state, skip_reason "
        "FROM urls ORDER BY id",
    ) == [
        ("https://site.test/", 0, "seed", None, "fetched", None),
        ("https://site.test/amp", 2, "hyperlink", about_id, "queued", None),
        ("https://site.test/p", 2, "meta_refresh", about_id, "queued", None),
        ("https://site.test/q", 1, "hyperlink", seed_id, "skipped", "nofollow"),
        ("https://site.test/out", 1, "hyperlink", seed_id, "skipped", "excluded"),
        ("https://site.test/about", 1, "hyperlink", seed_id, "fetched", None),
    ]


def _plan_of_first_statement(connection: Connection, run: Any) -> str:
    statements: list[tuple[str, Any]] = []

    def keep(_: Any, __: Any, sql: str, parameters: Any, *args: Any) -> None:
        statements.append((sql, parameters))

    event.listen(connection, "before_cursor_execute", keep)
    run(connection)
    event.remove(connection, "before_cursor_execute", keep)
    sql, parameters = statements[0]
    driver = connection.connection.driver_connection
    assert driver is not None
    rows = driver.execute(f"EXPLAIN QUERY PLAN {sql}", parameters).fetchall()
    return " | ".join(row[3] for row in rows)


def test_the_frontier_read_uses_its_index(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with opening(crawl.path, role="read") as engine, engine.connect() as connection:
        plan = _plan_of_first_statement(connection, queued_batch(1, 0, 10))

    assert ("USING INDEX urls_crawl_depth_id" in plan, "TEMP B-TREE" in plan) == (True, False), plan
