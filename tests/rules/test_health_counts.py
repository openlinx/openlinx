"""The Health Score of a crawl file's Pages (040-add-rules D8; seam 2)."""

import asyncio

from spider.aio import loop_factory
from spider.rules.registry import RULES
from spider.store.issues import INTERNAL_PAGES, STORED_AFFECTED_URLS, health, materialise_issues
from spider.store.reading import reading
from spider.store.records import Health
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.rules import crawl_with_pages
from tests.support.workspace import TempWorkspace


def test_warnings_do_not_lower_the_score(temp_workspace: TempWorkspace) -> None:
    # Over plain HTTP, both Pages are Affected URLs of http-url, a Warning, and of no Issue.
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {"title_count": 1, "title_1": "Shoes", "title_1_length": 5},
        {"title_count": 1, "title_1": "Boots", "title_1_length": 5},
        base="http://site.test/",
    )
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        asyncio.run(materialise_issues(writer, RULES), loop_factory=loop_factory)

    with reading(crawl_file) as connection:
        found = health(connection, INTERNAL_PAGES, STORED_AFFECTED_URLS)

    assert found == Health(score=100, internal_pages=2, affected_pages=0)
