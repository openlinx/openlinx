"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from functools import partial

from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext, handler
from openlinx.crawl.pages.preparation import InProcessExecutor, PageExecutor
from openlinx.extract.content_area import ContentArea
from openlinx.extract.link_handler import link_rows
from openlinx.extract.page_data import page_data_extractor
from openlinx.extract.page_handler import cookie_rows, page_rows
from openlinx.extract.page_links import PAGE_LINKS
from openlinx.extract.settings import ContentAreaSettings
from openlinx.store.links import inlink_ranges, write_inlinks, write_links
from openlinx.store.pages import write_cookies, write_pages
from openlinx.workspace.settings import Settings


def default_hooks(settings: Settings | None = None) -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here. Their configs come
    from the Crawl's loaded settings, or are the defaults without them."""
    area = ContentArea() if settings is None else settings.table(ContentAreaSettings).content_area()
    return Hooks(
        extractors=(page_data_extractor(area), PAGE_LINKS),
        handlers=(
            handler("pages", page_rows, write_pages),
            handler("cookies", cookie_rows, write_cookies),
            handler("links", link_rows, write_links),
        ),
        passes=(Pass("inlinks", count_inlinks),),
    )


async def count_inlinks(context: PassContext) -> None:
    """The inlink pass (030-add-page-data D6): it only orders the store's units."""
    for first, last in await context.writer.run_async(inlink_ranges):
        await context.writer.submit_async(partial(write_inlinks, first, last))
    await context.writer.flush_async()


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
