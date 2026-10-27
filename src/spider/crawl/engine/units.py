"""A URL's unit: its final state, as its handlers see it, and its record (020-add-crawl-core D5)."""

import asyncio
from dataclasses import dataclass, replace
from typing import Any

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import (
    parse_failure,
    warn_of_a_blocked_seed,
    warn_of_an_unreachable_robots_txt,
    warn_of_possible_blocking,
    warn_of_seed_base_mismatch,
    warn_of_seed_redirected_off_site,
)
from spider.crawl.engine.discovery import discovered_urls
from spider.crawl.engine.hooks import Handler, UrlFailure, UrlResponse, UrlResult
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.seed_chain import SeedChain
from spider.crawl.fetch.fetcher import FetchFailure, FetchResult
from spider.crawl.fetch.politeness import BlockingRuns, RequestLimits
from spider.crawl.fetch.requester import Requester, UrlLimitRefused
from spider.crawl.following import RESOURCES, redirect_target
from spider.crawl.pages.preparation import (
    PageSettings,
    is_html_type,
    response_directives,
    response_links,
)
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.robots.reader import OriginRobots
from spider.crawl.scope import ScopeDecision
from spider.crawl.urls import NormalizedUrl, url_host, url_origin
from spider.output.codes import HANDLER_FAILED, PARSE_FAILED
from spider.output.diagnostics import Diagnostic
from spider.store.crawls import record_scope
from spider.store.records import (
    ErroredUrl,
    FetchedUrl,
    NewUrl,
    QueuedUrl,
    SkippedUrl,
    SkipReason,
)
from spider.store.rows import HandlerRows
from spider.store.urls import (
    UrlUnit,
    reclassify_urls,
    record_error,
    record_fetched,
    record_skipped,
)


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
    seed_chain: SeedChain


def via_resource(queued: QueuedUrl) -> bool:
    return queued.chain_via in RESOURCES


async def unit_of(
    run: Run, queued: QueuedUrl, decision: ScopeDecision
) -> tuple[UrlResult, UrlUnit] | None:
    """The URL's final state as its handlers see it, which a fallback unit keeps part of,
    and the unit that records it with their rows; or None when the URL limit refuses a new
    request, which leaves it queued. `decision` is taken once, at dispatch, so a URL found
    on several Pages is recorded once (design D1)."""
    # The Seed's Redirect Chain is depth 0: a redirect target keeps its source's depth.
    in_chain = run.seed_chain.is_open and queued.crawl_depth == 0
    if in_chain:
        run.seed_chain.join(queued.id, queued.url)
    recorded = await _outcome(run, queued, decision, in_chain)
    response = None if recorded is None else recorded[0].response
    # The chain ended without a response of its own: a failure or a skip.
    if (
        in_chain
        and run.seed_chain.is_open
        and recorded is not None
        and (response is None or response.redirect_target is None)
    ):
        await close_seed_chain(run, queued.url, responded=False)
    return recorded


async def close_seed_chain(run: Run, final_url: NormalizedUrl, *, responded: bool) -> None:
    """Closes the Seed's Redirect Chain on the URL it ended on: its URLs are decided again
    against the Scope it ended in, which the Crawl records when it widened, and page
    preparation starts with that Scope (022-add-fetch-policy D3)."""
    context = run.context
    if run.seed_chain.scope.is_off_site(final_url):
        warn_of_seed_redirected_off_site(context, run.seed_chain.seed, final_url)
    widened, decisions = run.seed_chain.close(final_url, responded=responded)
    await context.writer.run_async(reclassify_urls(decisions))
    if widened is not None:
        await context.writer.run_async(record_scope(widened.to_json()))
    await context.pages.start(
        PageSettings(
            scope=run.seed_chain.scope,
            extractors=context.hooks.extractors,
            robots_token=context.settings.robots_user_agent,
            follow_nofollow=context.settings.follow_nofollow,
            strip_params=context.strip_params,
        )
    )


async def _outcome(
    run: Run, queued: QueuedUrl, decision: ScopeDecision, in_chain: bool
) -> tuple[UrlResult, UrlUnit] | None:
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
            failure = UrlFailure(
                fetch_error=origin_robots.fetch_error,
                fetch_error_message=message,
                fetched_at=None,
            )
            return _errored(context, dispatched, failure)
        skip_reason, blocked = _robots_verdict(context, origin_robots, queued, decision)
    decided = replace(dispatched, blocked_by_robots_txt=blocked)
    if skip_reason is not None:
        skipped = replace(decided, fetch_state="skipped", skip_reason=skip_reason)
        # Not final: a shorter path re-queues it, and its handlers see it then (D5).
        rows = () if skip_reason == "max_depth" else _handler_rows(context, skipped)
        return skipped, record_skipped(_skipped_record(skipped, skip_reason, rows))
    attempted = await run.requester.request_url(queued.url)
    if isinstance(attempted, UrlLimitRefused):
        return None
    response = attempted.outcome
    decided = replace(decided, attempt_count=attempted.attempt_count)
    host = url_host(queued.url)
    status_code = None if isinstance(response, FetchFailure) else response.status_code
    if decision.is_internal and run.blocking.responded(host, status_code):
        warn_of_possible_blocking(context, host)
    if isinstance(response, FetchFailure):
        failure = UrlFailure(
            fetch_error=response.fetch_error,
            fetch_error_message=response.message,
            fetched_at=response.fetched_at,
        )
        return _errored(context, decided, failure)
    return await _fetched(run, decided, response, in_chain)


def _errored(
    context: CrawlContext, decided: UrlResult, failure: UrlFailure
) -> tuple[UrlResult, UrlUnit]:
    failed = replace(decided, fetch_state="error", failure=failure)
    rows = _handler_rows(context, failed)
    return failed, record_error(_errored_record(failed, failure, rows))


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
    run: Run, decided: UrlResult, response: FetchResult, in_chain: bool
) -> tuple[UrlResult, UrlUnit]:
    context, url = run.context, decided.url
    content_type = response.header("Content-Type")
    location = response.header("Location") if 300 <= response.status_code < 400 else None
    target = redirect_target(url, response.status_code, location, context.strip_params)
    if in_chain and target is None:
        # Before any preparation: the chain's last response may be a Page of the wider Scope.
        await close_seed_chain(run, url, responded=True)
    scope = run.seed_chain.scope
    # An External URL or one outside the Scope is a Checked URL, never parsed (design D5).
    followed = decided.in_scope and 200 <= response.status_code < 300
    prepared = followed and is_html_type(content_type)
    page = await context.pages.prepare(url, response) if prepared else None
    parsed = page is not None and page.parsed
    # The Link and Refresh headers of an in-Scope 2xx response count, whatever became of its
    # preparation (design D9).
    links = response_links(url, response, scope, context.strip_params) if followed else ()
    if page is not None:
        links += page.document_links
    if page is not None and page.parsed:
        directives = page.directives
    else:
        # The X-Robots-Tag applies to any response, a PDF's or a failed Page's (D9).
        directives = response_directives(response, context.settings.robots_user_agent)
    discovered = discovered_urls(links, scope)
    # The Page the Seed's Redirect Chain ends on, the Seed's own when it answered at once.
    if parsed and in_chain:
        warn_of_seed_base_mismatch(context, url, links, scope)
    parse_error = None if page is None else page.parse_error
    parse_error_message = None if page is None else page.parse_error_message
    if parse_error is not None:
        failure = parse_failure(url, parse_error, parse_error_message)
        context.reporter.count(Diagnostic.of(PARSE_FAILED, failure), url)
    url_response = UrlResponse(
        status_code=response.status_code,
        reason=response.reason,
        content_type=content_type,
        headers=response.headers,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        directives=directives,
        redirect_target=target,
    )
    fetched = replace(
        decided,
        fetch_state="fetched",
        response=url_response,
        parsed=parsed,
        parse_error=parse_error,
        parse_error_message=parse_error_message,
        links=links,
        outputs={} if page is None else dict(page.outputs),
    )
    rows = _handler_rows(context, fetched)
    redirect = (
        None
        if target is None
        else _redirect(target, run.seed_chain.decide(target, in_chain=in_chain))
    )
    record = _fetched_record(
        fetched, url_response, discovered, rows, location=location, redirect=redirect
    )
    return fetched, record_fetched(record)


# Each record reads its values from the UrlResult, and from the outcome's record in it.
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
    failed: UrlResult, failure: UrlFailure, rows: tuple[HandlerRows[Any], ...]
) -> ErroredUrl:
    return ErroredUrl(
        url_id=failed.url_id,
        fetch_error=failure.fetch_error,
        fetch_error_message=failure.fetch_error_message,
        fetched_at=failure.fetched_at,
        attempt_count=failed.attempt_count,
        blocked_by_robots_txt=failed.blocked_by_robots_txt,
        rows=rows,
    )


def _fetched_record(
    fetched: UrlResult,
    response: UrlResponse,
    discovered: tuple[NewUrl, ...],
    rows: tuple[HandlerRows[Any], ...],
    *,
    location: str | None,
    redirect: NewUrl | None,
) -> FetchedUrl:
    return FetchedUrl(
        url_id=fetched.url_id,
        status_code=response.status_code,
        content_type=response.content_type,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        attempt_count=fetched.attempt_count,
        redirect_location=location,
        redirect=redirect,
        parsed=fetched.parsed,
        parse_error=fetched.parse_error,
        parse_error_message=fetched.parse_error_message,
        blocked_by_robots_txt=fetched.blocked_by_robots_txt,
        discovered=discovered,
        rows=rows,
    )


def _redirect(target: NormalizedUrl, decision: ScopeDecision) -> NewUrl:
    # No Link: the Scope, robots.txt and the depth limit decide it at dispatch, as any URL.
    return NewUrl(
        url=target,
        discovered_via="redirect",
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
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
