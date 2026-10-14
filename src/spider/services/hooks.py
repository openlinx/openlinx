"""The composition root of a Crawl's hooks: the crawl core never imports them (020 D9)."""

from functools import partial

from spider.crawl.hooks import Handler, Hooks, Pass
from spider.crawl.pages import InProcessExecutor, PageExecutor
from spider.extract.page_data import PAGE_DATA
from spider.extract.page_handler import page_rows
from spider.rules.registry import RULES
from spider.store.issues import materialise_issues
from spider.store.page_records import PageRow
from spider.store.pages import write_page


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks(
        extractors=(PAGE_DATA,),
        handlers=(Handler("pages", page_rows),),
        passes=(Pass("issues", partial(materialise_issues, catalogue=RULES)),),
        row_writers={PageRow: write_page},
    )


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
