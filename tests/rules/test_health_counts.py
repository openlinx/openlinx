"""The Health Score of a crawl file's Pages (040-add-rules D8; seam 2)."""

import asyncio

from sqlalchemy import select

from spider.aio import loop_factory
from spider.rules.registry import RULES
from spider.rules.titles import TITLE_MISSING
from spider.store.crawls import record_state
from spider.store.issues import (
    INTERNAL_PAGES,
    STORED_AFFECTED_URLS,
    health,
    health_affected_in,
    materialise_issues,
)
from spider.store.reading import reading
from spider.store.records import Health
from spider.store.schema import affected_urls, crawl, pages
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.page_data import page_data
from tests.support.rules import TITLE_MULTIPLE, crawl_with_page, crawl_with_pages, recorded
from tests.support.workspace import TempWorkspace

UNTITLED = page_data("<h1>Sale</h1><p>Everything half price this week.</p>")
SHOES = page_data("<title>Running shoes</title>")
BOOTS = page_data("<title>Trail boots</title>")
SOCKS = page_data("<title>Wool socks</title>")


def test_warnings_do_not_lower_the_score(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(temp_workspace, SHOES, BOOTS, base="http://site.test/")
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)

    with reading(crawl_file) as connection:
        http_urls = connection.execute(
            select(affected_urls.c.url_id).where(affected_urls.c.rule_id == "http-url")
        ).all()
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)

    # Over plain HTTP, both Pages are Affected URLs of http-url, a Warning, and of no Issue.
    assert (len(http_urls), found) == (2, Health(score=100, internal_pages=2, affected_pages=0))


def test_a_page_with_several_issues_counts_once(temp_workspace: TempWorkspace) -> None:
    # A theme's empty <title> and an SEO plugin's own: title-missing fires on the empty first
    # one and title-multiple, of a crawl file of a later tool, on the two.
    doubled = page_data("<title></title><title>Running shoes</title>")
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        doubled,
        BOOTS,
        SOCKS,
        page_data("<title>Sandals</title>"),
        more_rules=(recorded(TITLE_MULTIPLE),),
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        later = (*RULES, TITLE_MULTIPLE)
        asyncio.run(materialise_issues(writer, later, FakeClock()), loop_factory=loop_factory)

    with reading(crawl_file) as connection:
        fired: list[str] = sorted(
            connection.execute(
                select(affected_urls.c.rule_id).where(affected_urls.c.rule_id.like("title-%"))
            ).scalars()
        )
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)

    assert (doubled["title_count"], doubled["title_1"], fired, found) == (
        2,
        "",
        ["title-missing", "title-multiple"],
        Health(score=75, internal_pages=4, affected_pages=1),
    )


def test_health_score_of_a_segment(temp_workspace: TempWorkspace) -> None:
    # The fifth Page, outside the Segment, is untitled too.
    crawl_file, ids = crawl_with_pages(temp_workspace, UNTITLED, SHOES, BOOTS, SOCKS, UNTITLED)
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES, FakeClock()), loop_factory=loop_factory)
    segment = select(pages.c.url_id).where(pages.c.url_id.in_(ids[:4]))

    with reading(crawl_file) as connection:
        found = health(connection, segment, STORED_AFFECTED_URLS)

    assert found == Health(score=75, internal_pages=4, affected_pages=1)


def test_live_health_score_of_a_running_crawl(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(temp_workspace, UNTITLED, SHOES)

    with reading(crawl_file) as connection:
        state: str = connection.execute(select(crawl.c.state)).scalar_one()
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert (state, found) == ("running", Health(score=50, internal_pages=2, affected_pages=1))


def test_a_disabled_rule_does_not_lower_the_live_score(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, disabled={TITLE_MISSING.id}, **UNTITLED)

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert found == Health(score=100, internal_pages=1, affected_pages=0)


def test_a_finished_crawl_is_scored_from_its_stored_issues(
    temp_workspace: TempWorkspace,
) -> None:
    # A crawl file of a later tool, whose pass stored title-multiple's Affected URLs.
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        page_data("<title>Running shoes</title><title>Running shoes | Shop</title>"),
        BOOTS,
        more_rules=(recorded(TITLE_MULTIPLE),),
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        later = (*RULES, TITLE_MULTIPLE)
        asyncio.run(materialise_issues(writer, later, FakeClock()), loop_factory=loop_factory)
        writer.run(record_state("completed", FakeClock().now()))

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, health_affected_in(connection, RULES))

    assert found == Health(score=50, internal_pages=2, affected_pages=1)
