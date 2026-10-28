"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from spider.crawl.engine.hooks import Hooks, handler
from spider.crawl.pages.preparation import InProcessExecutor, PageExecutor
from spider.extract.page_data import PAGE_DATA
from spider.extract.page_handler import cookie_rows, page_rows
from spider.store.pages import write_cookies, write_pages


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks(
        extractors=(PAGE_DATA,),
        handlers=(
            handler("pages", page_rows, write_pages),
            handler("cookies", cookie_rows, write_cookies),
        ),
    )


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
