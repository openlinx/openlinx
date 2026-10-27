"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from spider.crawl.engine.hooks import Hooks, Pass, PassContext, handler
from spider.crawl.pages.preparation import InProcessExecutor, PageExecutor
from spider.extract.page_data import PAGE_DATA
from spider.extract.page_handler import page_rows
from spider.rules.passes import materialise_issues
from spider.rules.registry import RULES
from spider.store.pages import write_pages


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks(
        extractors=(PAGE_DATA,),
        handlers=(handler("pages", page_rows, write_pages),),
        passes=(Pass("issues", _issues),),
    )


async def _issues(context: PassContext) -> None:
    await materialise_issues(context.writer, RULES, context.clock)


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
