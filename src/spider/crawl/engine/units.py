"""A URL's unit: its final state, as its handlers see it, and its record (020-add-crawl-core D5)."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import (
    parse_failure,
    warn_of_a_blocked_seed,
    warn_of_an_unreachable_robots_txt,
    warn_of_possible_blocking,
    warn_of_seed_base_mismatch,
)
from spider.crawl.engine.discovery import RESOURCES, discovered_urls
from spider.crawl.engine.hooks import Handler, UrlResult
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.fetch.fetcher import FetchFailure, FetchResult
from spider.crawl.fetch.politeness import BlockingRuns, RequestLimits
from spider.crawl.fetch.requester import Requester, UrlLimitRefused
from spider.crawl.pages.preparation import is_html_type, response_links
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.robots.reader import OriginRobots
from spider.crawl.scope import ScopeDecision
from spider.crawl.urls import url_host, url_origin
from spider.output.codes import HANDLER_FAILED, PARSE_FAILED
from spider.output.diagnostics import Diagnostic
from spider.store.records import (
    ErroredUrl,
    FetchedUrl,
    FetchError,
    NewUrl,
    QueuedUrl,
    SkippedUrl,
    SkipReason,
)
from spider.store.rows import HandlerRows
from spider.store.urls import UrlUnit, record_error, record_fetched, record_skipped


@dataclass(frozen=True, slots=True, kw_only=True)
class Run:
    """One run's dependencies, made once by run_crawl."""

    context: CrawlContext
    outcomes: Outcomes
    limits: RequestLimits
    requester: Requester
    robots: RobotsLoader
    blocking: BlockingRuns
    # The tasks of Checked URLs in flight, which never hold the depth barrier (design D3).
    checked_urls: set[asyncio.Task[None]]


def via_resource(queued: QueuedUrl) -> bool:
    return queued.discovered_via in RESOURCES


async def unit_of(
    run: Run, queued: QueuedUrl, decision: ScopeDecision
) -> tuple[UrlResult, UrlUnit] | None:
    """The URL's final state as its handlers see it, which a fallback unit keeps part of,
    and the unit that records it with their rows; or None when the URL limit refuses a new
    request, which leaves it queued. `decision` is taken once, at dispatch, so a URL found
    on several Pages is recorded once (design D1)."""
    context, robots = run.context, run.robots
    dispatched = _dispatched(queued, decision)
    skip_reason = _skip_reason(context, queued, decision)
    # Only a URL that would be requested is checked against robots.txt, so a skip never
    # requests it.
    blocked = None
    if skip_reason is None:
        # A verdict already requested decides the URL before the limit, which guards only a
        # new request (design D6).
        if not robots.requested(queued.url) and run.limits.refuse_if_full():
            return None
        # Before the URL's own host slot, which the robots.txt request of its origin takes.
        origin_robots = await robots.robots_of(queued.url)
        if origin_robots.fetch_error is not None:
            # The origin cannot be reached: the URL gets the error without a request of
            # its own (design D6).
            message = (
                f"The robots.txt request of {url_origin(queued.url)} got no HTTP response, "
                f"so the URL was not requested: {origin_robots.fetch_error_message}"
            )
            return _errored(context, dispatched, origin_robots.fetch_error, message, None)
        skip_reason, blocked = _robots_verdict(context, origin_robots, queued, decision)
    decided = replace(dispatched, blocked_by_robots_txt=blocked)
    if skip_reason is not None:
        skipped = replace(decided, fetch_state="skipped", skip_reason=skip_reason)
        # Not final: a shorter path re-queues it, and its handlers see it then (D5).
        rows = () if skip_reason == "max_depth" else _handler_rows(context, skipped)
        return skipped, record_skipped(_skipped_record(skipped, skip_reason, rows))
    response = await run.requester.request_url(queued.url)
    if isinstance(response, UrlLimitRefused):
        return None
    host = url_host(queued.url)
    status_code = None if isinstance(response, FetchFailure) else response.status_code
    if decision.is_internal and run.blocking.responded(host, status_code):
        warn_of_possible_blocking(context, host)
    if isinstance(response, FetchFailure):
        return _errored(
            context, decided, response.fetch_error, response.message, response.fetched_at
        )
    return await _fetched(context, decided, response)


def _errored(
    context: CrawlContext,
    decided: UrlResult,
    fetch_error: FetchError,
    message: str,
    fetched_at: datetime | None,
) -> tuple[UrlResult, UrlUnit]:
    failed = replace(
        decided,
        fetch_state="error",
        fetch_error=fetch_error,
        fetch_error_message=message,
        fetched_at=fetched_at,
    )
    rows = _handler_rows(context, failed)
    return failed, record_error(_errored_record(failed, fetch_error, message, rows))


def _robots_verdict(
    context: CrawlContext, origin_robots: OriginRobots, queued: QueuedUrl, decision: ScopeDecision
) -> tuple[SkipReason | None, bool | None]:
    """robots.txt's skip of a URL that would be requested, and its blocked_by_robots_txt, NULL
    while the rules are unknown (design D6)."""
    ignore = context.settings.ignore_robots
    if origin_robots.state == "unreachable":
        if decision.is_internal:
            warn_of_an_unreachable_robots_txt(context, queued.url, origin_robots.status_code)
        return (None, None) if ignore else ("robots_unreachable", None)
    blocked = not origin_robots.allows(queued.url)
    # --ignore-robots requests it, still labelled as blocked.
    if blocked and not ignore:
        if queued.discovered_via == "seed":
            warn_of_a_blocked_seed(context, queued.url)
        return "blocked_by_robots_txt", True
    return None, blocked


def _skip_reason(
    context: CrawlContext, queued: QueuedUrl, decision: ScopeDecision
) -> SkipReason | None:
    max_depth = context.settings.max_depth
    if decision.skip_reason is not None:
        return decision.skip_reason
    # A followed Page's Resources are requested one deeper than the limit, no deeper: what
    # a Checked URL that was HTML links to is two deeper (design D5).
    if max_depth is not None and queued.crawl_depth > max_depth + via_resource(queued):
        return "max_depth"
    if not (decision.is_internal or context.settings.check_external):
        return "external_not_checked"
    return None


async def _fetched(
    context: CrawlContext, decided: UrlResult, response: FetchResult
) -> tuple[UrlResult, UrlUnit]:
    url = decided.url
    content_type = response.header("Content-Type")
    # An External URL or one outside the Scope is a Checked URL, never parsed (design D5).
    followed = decided.in_scope and 200 <= response.status_code < 300
    prepared = followed and is_html_type(content_type)
    page = await context.pages.prepare(url, response) if prepared else None
    parsed = page is not None and page.parsed
    # The Link and Refresh headers of an in-Scope 2xx response count, whatever became of its
    # preparation (design D9).
    links = response_links(url, response, context.scope, context.strip_params) if followed else ()
    if page is not None:
        links += page.document_links
    nofollow = page is not None and page.directives.nofollow
    discovered = discovered_urls(
        links,
        context.scope,
        nofollow=nofollow,
        follow_nofollow=context.settings.follow_nofollow,
    )
    if parsed and decided.discovered_via == "seed":
        warn_of_seed_base_mismatch(context, url, links)
    parse_error = None if page is None else page.parse_error
    parse_error_message = None if page is None else page.parse_error_message
    if parse_error is not None:
        failure = parse_failure(url, parse_error, parse_error_message)
        context.reporter.count(Diagnostic.of(PARSE_FAILED, failure), url)
    fetched = replace(
        decided,
        fetch_state="fetched",
        status_code=response.status_code,
        content_type=content_type,
        response_time_ms=response.response_time_ms,
        fetched_at=response.fetched_at,
        parsed=parsed,
        parse_error=parse_error,
        parse_error_message=parse_error_message,
        headers=response.headers,
        outputs={} if page is None else dict(page.outputs),
    )
    rows = _handler_rows(context, fetched)
    return fetched, record_fetched(_fetched_record(fetched, response, discovered, rows))


# Each record reads from the UrlResult every field it shares with it; a field that the
# record narrows comes from the value that set it in the UrlResult.
def _skipped_record(
    skipped: UrlResult, skip_reason: SkipReason, rows: tuple[HandlerRows[Any], ...]
) -> SkippedUrl:
    return SkippedUrl(
        url_id=skipped.url_id,
        skip_reason=skip_reason,
        crawl_depth=skipped.crawl_depth,
        blocked_by_robots_txt=skipped.blocked_by_robots_txt,
        rows=rows,
    )


def _errored_record(
    failed: UrlResult,
    fetch_error: FetchError,
    message: str,
    rows: tuple[HandlerRows[Any], ...],
) -> ErroredUrl:
    return ErroredUrl(
        url_id=failed.url_id,
        fetch_error=fetch_error,
        fetch_error_message=message,
        fetched_at=failed.fetched_at,
        blocked_by_robots_txt=failed.blocked_by_robots_txt,
        rows=rows,
    )


def _fetched_record(
    fetched: UrlResult,
    response: FetchResult,
    discovered: tuple[NewUrl, ...],
    rows: tuple[HandlerRows[Any], ...],
) -> FetchedUrl:
    return FetchedUrl(
        url_id=fetched.url_id,
        status_code=response.status_code,
        content_type=fetched.content_type,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        parsed=fetched.parsed,
        parse_error=fetched.parse_error,
        parse_error_message=fetched.parse_error_message,
        blocked_by_robots_txt=fetched.blocked_by_robots_txt,
        discovered=discovered,
        rows=rows,
    )


def _dispatched(queued: QueuedUrl, decision: ScopeDecision) -> UrlResult:
    """The URL as it is dispatched, still queued: each outcome replaces what it decides, which
    mypy checks field by field."""
    return UrlResult(
        url_id=queued.id,
        url=queued.url,
        crawl_depth=queued.crawl_depth,
        discovered_via=queued.discovered_via,
        found_on_url_id=queued.found_on_url_id,
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
        fetch_state="queued",
    )


def _handler_rows(context: CrawlContext, result: UrlResult) -> tuple[HandlerRows[Any], ...]:
    rows: list[HandlerRows[Any]] = []
    for handler in context.hooks.handlers:
        try:
            batch = _rows_of(handler, result)
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
            continue
        if batch is not None:
            rows.append(batch)
    return tuple(rows)


def _rows_of[R](handler: Handler[R], result: UrlResult) -> HandlerRows[R] | None:
    # Whole, or not at all: a handler that fails midway keeps none of its rows.
    rows = tuple(handler.handle(result))
    return HandlerRows(handler.write, rows) if rows else None
