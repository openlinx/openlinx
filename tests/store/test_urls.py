"""The units of spider.store.urls (020-add-crawl-core D1, D2, D14; seam 2)."""

from typing import Any

from sqlalchemy import Connection, event

from spider.crawl.urls import NormalizedUrl, parse_seed
from spider.store.connections import opening
from spider.store.records import NewUrl, QueuedUrl, UrlCounts
from spider.store.urls import next_depth, queued_batch, record_fetched, record_seed, url_counts
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def _url(text: str) -> NormalizedUrl:
    url = parse_seed(text)
    assert isinstance(url, str)
    return url


def _new(text: str) -> NewUrl:
    return NewUrl(url=_url(text), host="site.test", crawl_depth=1, discovered_via="hyperlink")


def test_the_units_of_urls_run_again_the_same(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    seed = _url("https://site.test/")
    found = [_new("https://site.test/a"), _new("https://site.test/b"), _new("https://site.test/a")]

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(seed, "site.test"))
        writer.run(record_seed(seed, "site.test"))
        first = writer.run(queued_batch(0, 0, 10))
        writer.run(record_fetched(seed_id, 200, parsed=True, discovered=found))
        deeper = writer.run(next_depth(0))
        second = writer.run(queued_batch(1, 0, 1))
        counts = writer.run(url_counts())
        replay_now(writer)

    assert (
        first,
        deeper,
        second,
        counts,
        query(
            crawl.path, "SELECT url, crawl_depth, fetch_state, status_code FROM urls ORDER BY id"
        ),
    ) == (
        (QueuedUrl(seed_id, seed),),
        1,
        (QueuedUrl(seed_id + 1, _url("https://site.test/a")),),
        UrlCounts(
            discovered=3,
            fetched=1,
            errors=0,
            skipped=0,
            queued=2,
            pages=1,
            status_2xx=1,
            status_3xx=0,
            status_4xx=0,
            status_5xx=0,
            status_other=0,
        ),
        [
            ("https://site.test/", 0, "fetched", 200),
            ("https://site.test/a", 1, "queued", None),
            ("https://site.test/b", 1, "queued", None),
        ],
    )


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
