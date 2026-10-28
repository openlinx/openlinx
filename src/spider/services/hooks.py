"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from spider.crawl.engine.hooks import Hooks, handler
from spider.crawl.pages.preparation import InProcessExecutor, PageExecutor
from spider.extract.content_area import ContentArea
from spider.extract.page_data import page_data_extractor
from spider.extract.page_handler import cookie_rows, page_rows
from spider.extract.settings import ContentAreaSettings
from spider.store.pages import write_cookies, write_pages
from spider.workspace.settings import Settings


def default_hooks(settings: Settings | None = None) -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here. Their configs come
    from the Crawl's loaded settings, or are the defaults without them."""
    area = ContentArea() if settings is None else settings.table(ContentAreaSettings).content_area()
    return Hooks(
        extractors=(page_data_extractor(area),),
        handlers=(
            handler("pages", page_rows, write_pages),
            handler("cookies", cookie_rows, write_cookies),
        ),
    )


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
