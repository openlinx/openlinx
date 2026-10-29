"""The composition root of a Crawl's hooks: the crawl core never imports them (020 D9)."""

from spider.crawl.hooks import Hooks
from spider.crawl.pages import InProcessExecutor, PageExecutor


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks()


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
