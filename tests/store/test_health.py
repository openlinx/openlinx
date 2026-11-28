"""Verify the Health Score of Internal Pages, including recorded Issue counts."""

from dataclasses import replace

import pytest
from sqlalchemy import create_engine, insert, literal, select
from sqlalchemy.pool import NullPool

from openlinx.rules.registry import RULES
from openlinx.store.health import (
    Health,
    health_for_pages,
    health_score,
    materialised_health,
    record_health,
)
from openlinx.store.issues import affected_urls_in
from openlinx.store.pages import write_pages
from openlinx.store.reading import reading
from openlinx.store.schema import affected_urls, metadata, origins, pages, rules, urls
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.crawls import query
from tests.support.page_data import page_row
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now


def test_pages_with_issue_type_issues_lower_the_score() -> None:
    assert health_score(internal_pages=10, affected_pages=3) == 70


def test_score_is_rounded_down() -> None:
    assert health_score(internal_pages=3, affected_pages=1) == 66


def test_health_score_is_undefined_without_internal_pages() -> None:
    assert health_score(internal_pages=0, affected_pages=0) is None


def test_materialised_health_preserves_zero_counts_without_pages() -> None:
    with create_engine("sqlite://", poolclass=NullPool).begin() as connection:
        metadata.create_all(connection, tables=[origins, urls, pages, rules, affected_urls])

        assert materialised_health(connection) == Health(
            score=None, internal_pages=0, affected_pages=0
        )


def test_resource_issues_do_not_change_the_score() -> None:
    with create_engine("sqlite://", poolclass=NullPool).begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        metadata.create_all(connection, tables=[origins, urls, pages, rules, affected_urls])
        connection.execute(
            insert(origins).values(
                id=1, origin="https://example.test", host="example.test", is_internal=True
            )
        )
        connection.execute(
            insert(urls).values(
                host="example.test",
                origin_id=1,
                is_internal=True,
                in_scope=True,
                fetch_state="fetched",
            ),
            [
                {
                    "id": 1,
                    "url": "https://example.test/",
                    "crawl_depth": 0,
                    "discovered_via": "seed",
                    "found_on_url_id": None,
                    "status_code": 200,
                    "content_type": "text/html",
                    "parsed": True,
                },
                {
                    "id": 2,
                    "url": "https://example.test/x.png",
                    "crawl_depth": 1,
                    "discovered_via": "image",
                    "found_on_url_id": 1,
                    "status_code": 404,
                    "content_type": "image/png",
                    "parsed": False,
                },
            ],
        )
        page = page_row(
            '<title>Home</title><img src="/x.png" alt="Logo">', url="https://example.test/"
        )
        write_pages(connection, [replace(page, url_id=1)])
        # Start with the materialised result. The image Rule is evaluated in its own slice.
        connection.execute(
            insert(rules).values(
                id="image-broken",
                category="images",
                issue_type="issue",
                priority="medium",
                applies_to="resources",
                enabled=True,
                thresholds={},
                description="Image Resources that fail to load.",
                why_it_matters="Broken images leave missing content.",
                how_to_fix="Restore the image or fix its URL.",
                reproduce_sql=(
                    "SELECT id AS url_id, json_object('status_code', status_code) AS detail "
                    "FROM urls WHERE discovered_via = 'image' AND status_code = 404"
                ),
            )
        )
        connection.execute(
            insert(affected_urls).values(
                rule_id="image-broken", url_id=2, detail={"status_code": 404}
            )
        )

        assert materialised_health(connection) == Health(
            score=100, internal_pages=1, affected_pages=0
        )


@pytest.mark.parametrize("completed", [True, False], ids=["materialised", "live"])
def test_health_score_of_a_segment(temp_workspace: TempWorkspace, completed: bool) -> None:
    file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/products/a": "<title>Product A</title>",
            "https://example.com/products/b": "<title>Product B</title>",
            "https://example.com/products/c": "<title>Product C</title>",
            "https://example.com/products/d": "<h1>Product D</h1>",
            "https://example.com/blog/post": "<h1>Blog post</h1>",
        },
        completed=completed,
    )
    segment_pages = select(pages.c.url_id).where(pages.c.url_path.like("/products/%"))

    with reading(file, snapshot=True) as connection:
        if completed:
            assert materialised_health(connection) == Health(
                score=66, internal_pages=6, affected_pages=2
            )
            result = health_for_pages(connection, page_ids=segment_pages)
        else:
            assert materialised_health(connection) == Health(
                score=100, internal_pages=6, affected_pages=0
            )
            found = affected_urls_in(connection, "title-missing", RULES).subquery()
            live = select(found.c.url_id, literal("title-missing").label("rule_id")).subquery()
            result = health_for_pages(connection, page_ids=segment_pages, affected=live)

    assert result == Health(score=75, internal_pages=4, affected_pages=1)


def test_health_replay_preserves_score_counts_and_timestamp(temp_workspace: TempWorkspace) -> None:
    file = crawl_store(
        temp_workspace,
        pages={
            "https://example.com/a": "<title>A</title><h1>A</h1>",
            "https://example.com/b": "<h1>B</h1>",
            "https://example.com/c": "<title>C</title><h1>C</h1>",
        },
    )
    clock = FakeClock()
    with CrawlWriter(file, clock) as writer:
        writer.run(record_health(clock.now()))
        clock.shift_wall(60)
        replay_now(writer)

    assert query(
        file,
        "SELECT health_score, health_internal_page_count, health_affected_page_count, "
        "health_calculated_at FROM crawl",
    ) == [(75, 4, 1, "2026-01-01T00:00:00.000Z")]
