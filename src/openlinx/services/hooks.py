"""Compose built-in Crawl hooks outside the crawl core."""

from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext, UrlResult, handler
from openlinx.crawl.pages.preparation import InProcessExecutor, PageExecutor
from openlinx.extract.content_area import ContentArea
from openlinx.extract.link_handler import link_rows
from openlinx.extract.page_data import page_data_extractor
from openlinx.extract.page_handler import cookie_rows, page_rows
from openlinx.extract.page_links import PAGE_LINKS
from openlinx.extract.settings import ContentAreaSettings
from openlinx.rules.registry import RULES
from openlinx.store.issues import affected_urls_unit, materialise_issues
from openlinx.store.links import (
    inlink_counts,
    inlink_ranges,
    pages_with_status_200,
    write_links,
)
from openlinx.store.pages import write_cookies, write_pages
from openlinx.store.records import ResponseHeaders
from openlinx.store.response_headers import write_response_headers
from openlinx.workspace.settings import Settings

# The installed catalogue supplies the SQL. Each Crawl records which Rule ids to run.
_RULE_UNITS = {rule.id: affected_urls_unit(rule) for rule in RULES}


def default_hooks(settings: Settings | None = None) -> Hooks:
    """Register built-in hooks here with configs from the Crawl's loaded settings, or their
    defaults when no settings are supplied."""
    area = ContentArea() if settings is None else settings.table(ContentAreaSettings).content_area()
    return Hooks(
        extractors=(page_data_extractor(area), PAGE_LINKS),
        handlers=(
            handler("pages", page_rows, write_pages),
            handler("cookies", cookie_rows, write_cookies),
            handler("links", link_rows, write_links),
            handler("response_headers", _response_headers, write_response_headers),
        ),
        passes=(
            Pass("inlinks", count_inlinks),
            Pass("issues", lambda context: materialise_issues(context.writer, _RULE_UNITS)),
        ),
    )


def _response_headers(result: UrlResult) -> tuple[ResponseHeaders, ...]:
    if result.response is None:
        return ()
    return (ResponseHeaders(url_id=result.url_id, headers=result.response.headers),)


async def count_inlinks(context: PassContext) -> None:
    """The inlink pass only orders the store's units; SQL stays in the store."""
    pages_200 = await context.writer.run_async(pages_with_status_200)
    for first, last in await context.writer.run_async(inlink_ranges):
        await context.writer.submit_async(inlink_counts(first, last, pages_200))
    await context.writer.flush_async()


def default_page_executor() -> PageExecutor:
    """Prepare Pages in process; 026-add-parse-pool owns the planned worker-process executor."""
    return InProcessExecutor()
