"""The engine: the frontier depth by depth, and each URL's unit (020-add-crawl-core D1, D2, D3)."""

from spider.crawl.context import CrawlContext
from spider.crawl.fetcher import FetchResult, Request
from spider.crawl.hooks import Hooks, UrlResult
from spider.crawl.pages import PreparedPage
from spider.crawl.scope import ScopeDecision, ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchedUrl, NewUrl, QueuedUrl, SkippedUrl
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
    hooks = context.hooks
    skip_reason = context.scope.decide(queued.url).skip_reason
    if skip_reason is not None:
        skipped = UrlResult(
            url_id=queued.id,
            url=queued.url,
            crawl_depth=depth,
            fetch_state="skipped",
            skip_reason=skip_reason,
        )
        unit = record_skipped(
            SkippedUrl(queued.id, skip_reason, _handled(hooks, skipped)), hooks.row_writers
        )
        await context.writer.submit_async(unit)
        return
    response = await context.fetcher.fetch(Request(queued.url))
    parsed = 200 <= response.status_code < 300 and _is_html(response)
    page = await context.pages.prepare(queued.url, response) if parsed else None
    discovered = () if page is None else _followed(page, context.scope, depth + 1)
    result = UrlResult(
        url_id=queued.id,
        url=queued.url,
        crawl_depth=depth,
        fetch_state="fetched",
        status_code=response.status_code,
        headers=response.headers,
        outputs={} if page is None else dict(page.outputs),
    )
    # The URL's task ends here; its outcome arrives at the commit (design D2).
    fetched = FetchedUrl(
        url_id=queued.id,
        status_code=response.status_code,
        content_type=response.header("Content-Type"),
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        parsed=parsed,
        parse_error=None if page is None else page.parse_error,
        parse_error_message=None if page is None else page.parse_error_message,
        discovered=discovered,
        rows=_handled(hooks, result),
    )
    await context.writer.submit_async(record_fetched(fetched, hooks.row_writers))


def _handled(hooks: Hooks, result: UrlResult) -> tuple[object, ...]:
    return tuple(row for handler in hooks.handlers for row in handler.handle(result))


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
