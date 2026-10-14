"""The composition root of a Crawl's hooks: the crawl core never imports them (020 D9)."""

from spider.crawl.hooks import Hooks
from spider.crawl.pages import PageExecutor
from spider.crawl.parse_pool import PoolExecutor


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks()


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in worker processes, always (026's decision of 2026-10-11)."""
    return PoolExecutor()
