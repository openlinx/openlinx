"""A URL's unit: its final state, as its handlers see it, and its record (020-add-crawl-core D5)."""

import asyncio
from dataclasses import dataclass, replace
from typing import Any

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import (
    blocked_seed,
    handler_failure,
    parse_failure,
    possible_blocking,
    robots_redirect_failure,
    seed_base_mismatch,
    unreachable_robots_txt,
)
from spider.crawl.engine.discovery import discovered_urls
from spider.crawl.engine.hooks import Handler, UrlFailure, UrlResponse, UrlResult
from spider.crawl.engine.outcomes import Outcomes, Recorded, provenance_of
from spider.crawl.engine.seed_chain import SeedChain, close_seed_chain
from spider.crawl.engine.stop import StopSignal
from spider.crawl.fetch.body import is_decodable
from spider.crawl.fetch.fetcher import FetchFailure, FetchResult
from spider.crawl.fetch.politeness import BlockingRuns, RequestLimits
from spider.crawl.fetch.requester import Requester, UrlLimitRefused
from spider.crawl.following import is_redirection, redirect_target
from spider.crawl.pages.preparation import (
    PreparedPage,
    is_html_type,
    response_directives,
    response_links,
)
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.robots.reader import OriginRobots
from spider.crawl.scope import ScopeDecision
from spider.crawl.settings import CrawlSettings
from spider.crawl.urls import NormalizedUrl, host_key, url_origin
from spider.output.diagnostics import Diagnostic
from spider.store.records import (
    RESOURCE_LINK_TYPES,
    ErroredUrl,
    FetchedUrl,
    NewUrl,
    QueuedUrl,
    Redirect,
    SkippedUrl,
    SkipReason,
)
from spider.store.rows import HandlerRows
from spider.store.urls import record_error, record_fetched, record_skipped
from spider.store.writer import CrawlWriterClosedError


class TaskFailure:
    """The first exception that escaped a URL's task: a bug, which ends the run (design D16)."""

    def __init__(self, stop: StopSignal) -> None:
        self._stop = stop
        self._error: BaseException | None = None

    @property
    def is_set(self) -> bool:
        return self._error is not None

    def track(self, tasks: set[asyncio.Task[None]], task: asyncio.Task[None]) -> None:
        tasks.add(task)
        task.add_done_callback(lambda done: self._ended(tasks, done))

    def raise_first(self) -> None:
        if self._error is not None:
            raise self._error

    def _ended(self, tasks: set[asyncio.Task[None]], task: asyncio.Task[None]) -> None:
        tasks.discard(task)
        if task.cancelled():
            return
        # Retrieved here, since a task that ends before a gather waits on it has already left
        # its set: unseen, its URL would stay queued and be dispatched again by every sweep.
        error = task.exception()
        if isinstance(error, CrawlWriterClosedError):
            # Not a bug: an ended writer refuses every unit, and its cause says why (017 D6).
            self._stop.set("write_failed", error.__cause__ or error)
        elif error is not None and self._error is None:
            self._error = error


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
    task_failure: TaskFailure


def via_resource(queued: QueuedUrl) -> bool:
    return queued.chain_via in RESOURCE_LINK_TYPES


async def unit_of(run: Run, queued: QueuedUrl, decision: ScopeDecision) -> Recorded | None:
    """The URL's final state as its handlers see it, which a fallback unit keeps part of,
    and the unit that records it with their rows; or None when the URL limit refuses a new
    request, which leaves it queued. `decision` is taken once, at dispatch, so a URL found
    on several Pages is recorded once (design D1)."""
    # The Seed's Redirect Chain is depth 0: a redirect target keeps its source's depth.
    in_chain = run.seed_chain.holds(queued)
    recorded = await _outcome(run, queued, decision, in_chain)
    response = None if recorded is None else recorded.result.response
    # The chain ended without a response of its own: a failure or a skip.
    if (
        in_chain
        and run.seed_chain.is_open
        and recorded is not None
        and (response is None or response.redirect_target is None)
    ):
        await close_seed_chain(run.context, run.seed_chain, responded=False)
    return recorded


async def _outcome(
    run: Run, queued: QueuedUrl, decision: ScopeDecision, in_chain: bool
) -> Recorded | None:
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
        origin_error = origin_robots.origin_error
        if origin_error is not None:
            # The origin cannot be reached: the URL gets the error without a request of
            # its own (design D6).
            message = (
                f"The robots.txt request of {url_origin(queued.url)} got no HTTP response, "
                f"so the URL was not requested: {origin_robots.fetch_error_message}"
            )
            failure = UrlFailure(
                fetch_error=origin_error,
                fetch_error_message=message,
                fetched_at=None,
            )
            return _errored(context, dispatched, failure)
        skip_reason, blocked, warnings = _robots_verdict(
            context.settings, origin_robots, queued, decision, in_chain
        )
        for warning in warnings:
            context.reporter.warn(warning)
    decided = replace(dispatched, blocked_by_robots_txt=blocked)
    if skip_reason is not None:
        skipped = replace(decided, fetch_state="skipped", skip_reason=skip_reason)
        # Not final: a shorter path re-queues it, and its handlers see it then (D5).
        rows, failed_handlers = (
            ((), None) if skip_reason == "max_depth" else _handler_rows(context, skipped)
        )
        return Recorded(
            skipped, record_skipped(_skipped_record(skipped, skip_reason, rows)), failed_handlers
        )
    attempted = await run.requester.request_url(queued.url)
    if isinstance(attempted, UrlLimitRefused):
        return None
    response = attempted.outcome
    decided = replace(decided, attempt_count=attempted.attempt_count)
    host = host_key(queued.url)
    status_code = None if isinstance(response, FetchFailure) else response.status_code
    if decision.is_internal and run.blocking.responded(host, status_code):
        context.reporter.warn(possible_blocking(host))
    if isinstance(response, FetchFailure):
        failure = UrlFailure(
            fetch_error=response.fetch_error,
            fetch_error_message=response.message,
            fetched_at=response.fetched_at,
        )
        return _errored(context, decided, failure)
    return await _fetched(run, decided, response, in_chain)


def _errored(context: CrawlContext, decided: UrlResult, failure: UrlFailure) -> Recorded:
    failed = replace(decided, fetch_state="error", failure=failure)
    rows, failed_handlers = _handler_rows(context, failed)
    unit = record_error(_errored_record(failed, failure, rows))
    return Recorded(failed, unit, failed_handlers)


def _robots_verdict(
    settings: CrawlSettings,
    origin_robots: OriginRobots,
    queued: QueuedUrl,
    decision: ScopeDecision,
    in_chain: bool,
) -> tuple[SkipReason | None, bool | None, tuple[Diagnostic, ...]]:
    """robots.txt's skip of a URL that would be requested, its blocked_by_robots_txt, NULL
    while the rules are unknown, and the warnings for the caller to give (design D6)."""
    ignore = settings.ignore_robots
    warnings: tuple[Diagnostic, ...] = ()
    if origin_robots.state == "unreachable":
        if decision.is_internal:
            status_code = origin_robots.status_code
            warnings = (unreachable_robots_txt(queued.url, status_code, ignore_robots=ignore),)
        return (None, None, warnings) if ignore else ("robots_unreachable", None, warnings)
    redirect_failure = origin_robots.redirect_failure
    if redirect_failure is not None and decision.is_internal:
        warnings = (robots_redirect_failure(queued.url, *redirect_failure),)
    blocked = not origin_robots.allows(queued.url)
    # --ignore-robots requests it, still labelled as blocked.
    if blocked and not ignore:
        # Any URL of the Seed's chain: the Seed answered with a redirect, its target is blocked.
        if in_chain:
            warnings += (blocked_seed(queued.url, settings.robots_user_agent),)
        return "blocked_by_robots_txt", True, warnings
    return None, blocked, warnings


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


async def _fetched(run: Run, decided: UrlResult, response: FetchResult, in_chain: bool) -> Recorded:
    context, url = run.context, decided.url
    content_type = response.header("Content-Type")
    location = response.header("Location") if is_redirection(response.status_code) else None
    target = redirect_target(url, response.status_code, location, context.strip_params)
    if in_chain and target is None:
        # Before any preparation: the chain's last response may be a Page of the wider Scope.
        await close_seed_chain(run.context, run.seed_chain, responded=True)
    scope = run.seed_chain.scope
    # An External URL or one outside the Scope is a Checked URL, never parsed (design D5).
    followed = decided.in_scope and 200 <= response.status_code < 300
    prepared = followed and is_html_type(content_type)
    content_encoding = response.header("Content-Encoding")
    decoded = is_decodable(content_encoding)
    if prepared and response.body_truncated:
        # A Page cut at the cap would be parsed as another, shorter one (022 design D1).
        page: PreparedPage | None = PreparedPage(
            parse_error="body_too_large",
            parse_error_message="The body is larger than 20 MiB.",
        )
    elif prepared and not decoded:
        # A server that ignored the offered codings: its bytes are no text to parse (D1).
        page = PreparedPage(
            parse_error="unsupported_encoding",
            parse_error_message=f"The body is in {content_encoding}, which no request offers.",
        )
    else:
        page = await context.pages.prepare(url, response) if prepared else None
    parsed = page is not None and page.parsed
    # The Link and Refresh headers of an in-Scope 2xx response count, whatever became of its
    # preparation (design D9).
    links = response_links(url, response, scope, context.strip_params) if followed else ()
    if page is not None:
        links += page.html_links
    if page is not None and page.parsed:
        directives = page.directives
    else:
        # The X-Robots-Tag applies to any response, a PDF's or a failed Page's (D9).
        directives = response_directives(response, context.settings.robots_user_agent)
    discovered = discovered_urls(links, scope)
    # The Page the Seed's Redirect Chain ends on, the Seed's own when it answered at once.
    if parsed and in_chain:
        mismatch = seed_base_mismatch(url, links, scope)
        if mismatch is not None:
            context.reporter.warn(mismatch)
    parse_error = None if page is None else page.parse_error
    parse_error_message = None if page is None else page.parse_error_message
    if parse_error is not None:
        context.reporter.count(parse_failure(url, parse_error, parse_error_message), url)
    url_response = UrlResponse(
        status_code=response.status_code,
        reason=response.reason,
        content_type=content_type,
        headers=response.headers,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        body_truncated=response.body_truncated,
        content_encoding=content_encoding,
        # Measured on the decoded body, unless the cap cut it or it was kept as received (D1).
        size_bytes=len(response.body) if decoded and not response.body_truncated else None,
        transferred_bytes=response.transferred_bytes,
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
    rows, failed_handlers = _handler_rows(context, fetched)
    redirect = (
        Redirect(
            location=location,
            target=None
            if target is None
            else _redirect(target, run.seed_chain.decide(target, in_chain=in_chain)),
            max_redirects=context.settings.max_redirects,
        )
        if is_redirection(response.status_code)
        else None
    )
    record = _fetched_record(fetched, url_response, discovered, rows, redirect=redirect)
    return Recorded(fetched, record_fetched(record), failed_handlers)


# Each record reads its values from the UrlResult, and from the outcome's record in it.
def _skipped_record(
    skipped: UrlResult, skip_reason: SkipReason, rows: tuple[HandlerRows[Any], ...]
) -> SkippedUrl:
    return SkippedUrl(
        url_id=skipped.url_id,
        skip_reason=skip_reason,
        provenance=provenance_of(skipped),
        blocked_by_robots_txt=skipped.blocked_by_robots_txt,
        rows=rows,
    )


def _errored_record(
    failed: UrlResult, failure: UrlFailure, rows: tuple[HandlerRows[Any], ...]
) -> ErroredUrl:
    return ErroredUrl(
        url_id=failed.url_id,
        provenance=provenance_of(failed),
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
    redirect: Redirect | None,
) -> FetchedUrl:
    return FetchedUrl(
        url_id=fetched.url_id,
        provenance=provenance_of(fetched),
        status_code=response.status_code,
        content_type=response.content_type,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        attempt_count=fetched.attempt_count,
        redirect=redirect,
        parsed=fetched.parsed,
        parse_error=fetched.parse_error,
        parse_error_message=fetched.parse_error_message,
        body_truncated=response.body_truncated,
        content_encoding=response.content_encoding,
        size_bytes=response.size_bytes,
        transferred_bytes=response.transferred_bytes,
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


def _handler_rows(
    context: CrawlContext, result: UrlResult
) -> tuple[tuple[HandlerRows[Any], ...], Diagnostic | None]:
    """The handlers' rows, and their failure, which counts once the unit records it."""
    rows: list[HandlerRows[Any]] = []
    failed: list[tuple[str, BaseException]] = []
    for handler in context.hooks.handlers:
        try:
            batch = _rows_of(handler, result)
        # A handler is later changes' code: its failure costs only its rows (design D16).
        except Exception as error:
            failed.append((handler.name, error))
            continue
        if batch is not None:
            rows.append(batch)
    # One count per URL, however many of its handlers failed (design D16).
    return tuple(rows), handler_failure(result.url, failed) if failed else None


def _rows_of[R](handler: Handler[R], result: UrlResult) -> HandlerRows[R] | None:
    # Whole, or not at all: a handler that fails midway keeps none of its rows.
    rows = tuple(handler.handle(result))
    return HandlerRows(handler.write, rows) if rows else None
