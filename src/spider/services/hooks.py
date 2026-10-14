"""The composition root of a Crawl's hooks: the crawl core never imports them (020 D9)."""

from spider.crawl.hooks import Handler, Hooks
from spider.extract.page_data import PAGE_DATA
from spider.extract.page_handler import page_rows
from spider.store.page_records import PageRow
from spider.store.pages import write_page


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks(
        extractors=(PAGE_DATA,),
        handlers=(Handler("pages", page_rows),),
        row_writers={PageRow: write_page},
    )
