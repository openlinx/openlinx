"""Crawls prepare Pages in process unless marked parse_pool (design D1 of 026-add-parse-pool).

The pool starts its workers for every Crawl, each a spawn process of Python with the parser, so a
CLI-level crawl test would pay their start and memory per crawl. Only the composition root's
choice is replaced, where the Crawl Service calls it; a test marked `parse_pool` keeps the pool.
"""

import pytest

from spider.crawl.pages import InProcessExecutor
from spider.services import crawling


@pytest.fixture(autouse=True)
def in_process_pages(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("parse_pool") is None:
        # Raises if the service stops calling this name, so the swap cannot silently lapse.
        monkeypatch.setattr(crawling, "default_page_executor", InProcessExecutor)
