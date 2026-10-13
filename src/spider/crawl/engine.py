"""The engine: the frontier depth by depth, and each URL's unit (020-add-crawl-core D1, D2, D3)."""

from spider.crawl.context import CrawlContext
from spider.crawl.fetcher import Request
from spider.crawl.pages import PreparedPage
from spider.crawl.scope import ScopeRules
from spider.crawl.urls import NormalizedUrl, url_host
from spider.store.records import NewUrl, QueuedUrl
from spider.store.urls import next_depth, queued_batch, record_fetched, record_seed

# Queued URLs read from the frontier at once.
FRONTIER_BATCH = 100


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    await context.writer.run_async(record_seed(seed, url_host(seed)))
    depth: int | None = 0
    while depth is not None:
        await _crawl_depth(context, depth)
        # Read after every unit submitted so far, so it sees the URLs they discovered.
        depth = await context.writer.run_async(next_depth(depth))


async def _crawl_depth(context: CrawlContext, depth: int) -> None:
    # The cursor of this run: a URL in flight is never read twice (design D1).
    after = 0
    while batch := await context.writer.run_async(queued_batch(depth, after, FRONTIER_BATCH)):
        for queued in batch:
            await _crawl_url(context, queued, depth)
        after = batch[-1].id


async def _crawl_url(context: CrawlContext, queued: QueuedUrl, depth: int) -> None:
    response = await context.fetcher.fetch(Request(queued.url))
    page = await context.pages.prepare(queued.url, response)
    discovered = _followed(page, context.scope, depth + 1)
    # The URL's task ends here; its outcome arrives at the commit (design D2).
    await context.writer.submit_async(record_fetched(queued.id, response.status_code, discovered))


def _followed(page: PreparedPage, scope: ScopeRules, depth: int) -> tuple[NewUrl, ...]:
    return tuple(
        NewUrl(
            url=link.target,
            host=url_host(link.target),
            crawl_depth=depth,
            discovered_via=link.type,
        )
        for link in page.links
        if link.type == "hyperlink" and scope.decide(link.target).in_scope
    )
