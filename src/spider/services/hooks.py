"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from spider.crawl.engine.hooks import Hooks
from spider.crawl.pages.preparation import InProcessExecutor, PageExecutor


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks()


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
