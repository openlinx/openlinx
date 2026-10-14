"""The engine: the frontier depth by depth, and each URL's unit (020-add-crawl-core D1, D2, D3)."""

from spider.crawl.context import CrawlContext
from spider.crawl.fetcher import FetchFailure, FetchResult, Request
from spider.crawl.hooks import UrlResult
from spider.crawl.pages import PreparedPage
from spider.crawl.scope import ScopeDecision, ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.output.codes import HANDLER_FAILED, PARSE_FAILED
from spider.output.diagnostics import Diagnostic
from spider.store.records import ErroredUrl, FetchedUrl, NewUrl, QueuedUrl, SkippedUrl
from spider.store.urls import (
    next_depth,
    queued_batch,
    record_error,
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
            SkippedUrl(queued.id, skip_reason, _handled(context, skipped)), hooks.row_writers
        )
        await context.writer.submit_async(unit)
        return
    response = await context.fetcher.fetch(Request(queued.url))
    if isinstance(response, FetchFailure):
        await _record_failure(context, queued, depth, response)
        return
    parsed = 200 <= response.status_code < 300 and _is_html(response)
    page = await context.pages.prepare(queued.url, response) if parsed else None
    discovered = () if page is None else _followed(page, context.scope, depth + 1)
    if page is not None and page.parse_error is not None:
        context.reporter.count(
            Diagnostic.of(
                PARSE_FAILED,
                f"An extractor failed on {queued.url} ({page.parse_error_message}); the Page "
                "was recorded without its output, and its Links were followed.",
            ),
            queued.url,
        )
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
        rows=_handled(context, result),
    )
    await context.writer.submit_async(record_fetched(fetched, hooks.row_writers))


async def _record_failure(
    context: CrawlContext, queued: QueuedUrl, depth: int, failure: FetchFailure
) -> None:
    result = UrlResult(
        url_id=queued.id,
        url=queued.url,
        crawl_depth=depth,
        fetch_state="error",
        fetch_error=failure.fetch_error,
    )
    errored = ErroredUrl(
        url_id=queued.id,
        fetch_error=failure.fetch_error,
        fetch_error_message=failure.message,
        fetched_at=failure.fetched_at,
        rows=_handled(context, result),
    )
    await context.writer.submit_async(record_error(errored, context.hooks.row_writers))


def _handled(context: CrawlContext, result: UrlResult) -> tuple[object, ...]:
    rows: list[object] = []
    for handler in context.hooks.handlers:
        try:
            rows.extend(handler.handle(result))
        # A handler is later changes' code: its failure costs only its rows (design D16).
        except Exception as error:
            context.reporter.count(
                Diagnostic.of(
                    HANDLER_FAILED,
                    f"The handler {handler.name} raised {type(error).__name__} on "
                    f"{result.url}; the URL was recorded without its rows.",
                ),
                result.url,
            )
    return tuple(rows)


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
