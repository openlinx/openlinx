"""The engine: the frontier depth by depth, and each URL's unit (020-add-crawl-core D1, D2, D3)."""

from spider.crawl.context import CrawlContext
from spider.crawl.fetcher import FetchResult, Request
from spider.crawl.pages import PreparedPage
from spider.crawl.scope import ScopeDecision, ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchedUrl, NewUrl, QueuedUrl
from spider.store.urls import (
    next_depth,
    queued_batch,
    record_fetched,
    record_seed,
    record_skipped,
)

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    await context.writer.run_async(record_seed(seed))
    depth: int | None = 0
    while depth is not None:
        await _crawl_depth(context, depth)
        # Read after every unit submitted so far, so it sees the URLs they discovered.
        depth = await context.writer.run_async(next_depth(depth))


async def _crawl_depth(context: CrawlContext, depth: int) -> None:
    # The cursor of this run: a URL in flight is never read twice (design D1).
    after = 0
    while batch := await context.writer.run_async(queued_batch(depth, after, _FRONTIER_BATCH)):
        for queued in batch:
            await _crawl_url(context, queued, depth)
        after = batch[-1].id


async def _crawl_url(context: CrawlContext, queued: QueuedUrl, depth: int) -> None:
    # Decided once, at dispatch, so a URL found on several Pages is recorded once (design D1).
    skip_reason = context.scope.decide(queued.url).skip_reason
    if skip_reason is not None:
        await context.writer.submit_async(record_skipped(queued.id, skip_reason))
        return
    response = await context.fetcher.fetch(Request(queued.url))
    parsed = 200 <= response.status_code < 300 and _is_html(response)
    discovered: tuple[NewUrl, ...] = ()
    if parsed:
        page = await context.pages.prepare(queued.url, response)
        discovered = _followed(page, context.scope, depth + 1)
    # The URL's task ends here; its outcome arrives at the commit (design D2).
    fetched = FetchedUrl(
        url_id=queued.id,
        status_code=response.status_code,
        content_type=response.header("Content-Type"),
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        parsed=parsed,
        discovered=discovered,
    )
    await context.writer.submit_async(record_fetched(fetched))


def _followed(page: PreparedPage, scope: ScopeRules, depth: int) -> tuple[NewUrl, ...]:
    return tuple(
        NewUrl(url=link.target, crawl_depth=depth, discovered_via=link.type)
        for link in page.links
        if link.type == "hyperlink" and _recorded(scope.decide(link.target))
    )


def _recorded(decision: ScopeDecision) -> bool:
    return decision.in_scope or decision.skip_reason is not None


def _is_html(response: FetchResult) -> bool:
    content_type = response.header("Content-Type") or ""
    return content_type.partition(";")[0].strip().lower() in _HTML_TYPES
