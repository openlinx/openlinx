"""The engine: the frontier depth by depth, and each URL's unit (020-add-crawl-core D1, D2, D3)."""

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

from spider.crawl.context import CrawlContext
from spider.crawl.discovery import RESOURCES, discovered_urls
from spider.crawl.fetcher import FetchFailure, FetchResult, Request
from spider.crawl.hooks import UrlResult
from spider.crawl.links import DiscoveredLink
from spider.crawl.pages import PageSettings, is_html_type, response_links
from spider.crawl.politeness import RequestLimits
from spider.crawl.scope import ScopeDecision, apex_seed_named_by_page
from spider.crawl.urls import NormalizedUrl, url_host
from spider.output.codes import (
    HANDLER_FAILED,
    PARSE_FAILED,
    RECORD_FAILED,
    SEED_BASE_MISMATCH,
)
from spider.output.diagnostics import Diagnostic
from spider.store.failures import is_one_urls_failure
from spider.store.records import (
    ErroredUrl,
    FetchedUrl,
    ParseError,
    QueuedUrl,
    SkippedUrl,
    SkipReason,
)
from spider.store.urls import (
    UrlUnit,
    next_depth,
    queued_batch,
    record_error,
    record_fetched,
    record_seed,
    record_skipped,
    record_unwritten,
)
from spider.store.writer import CrawlWriterClosedError

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100


class _Outcomes:
    """Every submitted unit's Future until its outcome has reached the engine (design D2)."""

    def __init__(self, context: CrawlContext) -> None:
        self._context = context
        self._pending: set[asyncio.Future[Any]] = set()

    async def submit(self, queued: QueuedUrl, unit: UrlUnit) -> None:
        future = await self._context.writer.submit_async(unit)
        self._pending.add(future)
        future.add_done_callback(lambda done: self._unit_done(queued, done))

    async def settled(self) -> None:
        """Waits for every outcome, fallback units included."""
        while self._pending:
            # The writer commits on its own only every 500 units or second of clock time.
            with suppress(CrawlWriterClosedError):
                # An ended writer has already failed every Future it held.
                await asyncio.to_thread(self._context.writer.flush)
            # Outcomes that the flush resolved have already left the set.
            if self._pending:
                await asyncio.wait(set(self._pending))

    def _unit_done(self, queued: QueuedUrl, done: asyncio.Future[None]) -> None:
        self._pending.discard(done)
        error = done.exception()
        if error is None:
            return
        if not is_one_urls_failure(error):
            self._context.stop.set("write_failed", error)
            return
        self._context.reporter.count(
            Diagnostic.of(
                RECORD_FAILED,
                f"Recording {queued.url} failed ({type(error).__name__}), so it was recorded "
                "as an error, without the URLs found on it and its handlers' rows.",
            ),
            queued.url,
        )
        fallback = asyncio.ensure_future(self._fall_back(queued, error))
        self._pending.add(fallback)
        fallback.add_done_callback(self._pending.discard)

    async def _fall_back(self, queued: QueuedUrl, error: BaseException) -> None:
        message = f"{type(error).__name__}: {error}"
        try:
            await (await self._context.writer.submit_async(record_unwritten(queued.id, message)))
        # A fallback that fails is the file's failure, not the URL's (design D2).
        except Exception as failure:
            self._context.stop.set("write_failed", failure)


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    outcomes = _Outcomes(context)
    limits = RequestLimits(context.settings.concurrency, context.pages.backlog)
    decision = context.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    # Once, with the final Scope: 022 moves this to the end of the Seed's Redirect Chain.
    await context.pages.start(
        PageSettings(
            scope=context.scope,
            extractors=context.hooks.extractors,
            strip_params=context.strip_params,
        )
    )
    checks: set[asyncio.Task[None]] = set()
    depth: int | None = 0
    try:
        while depth is not None and not context.stop.is_set:
            await _crawl_depth(context, outcomes, limits, checks, depth)
            # Read after every unit submitted so far, so it sees the URLs they discovered.
            depth = await context.writer.run_async(next_depth(depth))
            if depth is None:
                # A check that was in-Scope HTML may have found URLs, or a shorter path to them,
                # at a depth the frontier has passed: once every check has ended, the queue is
                # read from the top.
                await asyncio.gather(*checks)
                depth = await context.writer.run_async(next_depth(-1))
    # An ended writer refuses every unit; its cause says why it ended (017 D6).
    except CrawlWriterClosedError as closed:
        context.stop.set("write_failed", closed.__cause__ or closed)
    finally:
        await _cancelled(checks)
    await outcomes.settled()


async def _crawl_depth(
    context: CrawlContext,
    outcomes: _Outcomes,
    limits: RequestLimits,
    checks: set[asyncio.Task[None]],
    depth: int,
) -> None:
    """Returns once every followed URL's task of the depth has ended, so the next depth sees
    their URLs; the depth's checks join `checks` and run on."""
    running: set[asyncio.Task[None]] = set()
    try:
        # The cursor of this run: a URL in flight is never read twice (design D1).
        after = 0
        while batch := await context.writer.run_async(queued_batch(depth, after, _FRONTIER_BATCH)):
            for queued in batch:
                await limits.reserve_task()
                if context.stop.is_set:
                    limits.task_ended()
                    return
                decision = context.scope.decide(queued.url)
                task = asyncio.create_task(_crawl_url(context, outcomes, limits, queued, decision))
                # A check never holds the barrier (design D3); the sweep in run_crawl reads
                # what one finds after its depth has closed.
                tasks = checks if _is_check(queued, decision) else running
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            after = batch[-1].id
        if running:
            await asyncio.gather(*running)
    finally:
        await _cancelled(running)


async def _cancelled(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Retrieved, so that no "Task exception was never retrieved" reaches stderr.
    await asyncio.gather(*tasks, return_exceptions=True)


def _is_check(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or queued.discovered_via in RESOURCES


async def _crawl_url(
    context: CrawlContext,
    outcomes: _Outcomes,
    limits: RequestLimits,
    queued: QueuedUrl,
    decision: ScopeDecision,
) -> None:
    try:
        # The URL's task ends at the submit; its outcome arrives at the commit (design D2).
        await outcomes.submit(queued, await _unit_of(context, limits, queued, decision))
    finally:
        limits.task_ended()


async def _unit_of(
    context: CrawlContext, limits: RequestLimits, queued: QueuedUrl, decision: ScopeDecision
) -> UrlUnit:
    """The unit that records the URL's final state, with its handlers' rows; `decision` is
    taken once, at dispatch, so a URL found on several Pages is recorded once (design D1)."""
    row_writers = context.hooks.row_writers
    skip_reason = _skip_reason(context, queued, decision)
    if skip_reason is not None:
        skipped = _result(queued, decision, fetch_state="skipped", skip_reason=skip_reason)
        return record_skipped(
            SkippedUrl(queued.id, skip_reason, _handler_rows(context, skipped)), row_writers
        )
    async with limits.host(url_host(queued.url)), limits.request():
        response = await context.fetcher.fetch(Request(queued.url))
    if isinstance(response, FetchFailure):
        failed = _result(
            queued,
            decision,
            fetch_state="error",
            fetch_error=response.fetch_error,
            fetch_error_message=response.message,
            fetched_at=response.fetched_at,
        )
        errored = ErroredUrl(
            url_id=queued.id,
            fetch_error=response.fetch_error,
            fetch_error_message=response.message,
            fetched_at=response.fetched_at,
            rows=_handler_rows(context, failed),
        )
        return record_error(errored, row_writers)
    return record_fetched(await _fetched(context, queued, decision, response), row_writers)


def _skip_reason(
    context: CrawlContext, queued: QueuedUrl, decision: ScopeDecision
) -> SkipReason | None:
    max_depth = context.settings.max_depth
    if decision.skip_reason is not None:
        return decision.skip_reason
    if max_depth is not None and queued.crawl_depth > max_depth:
        return "max_depth"
    if not (decision.is_internal or context.settings.check_external):
        return "external_not_checked"
    return None


async def _fetched(
    context: CrawlContext, queued: QueuedUrl, decision: ScopeDecision, response: FetchResult
) -> FetchedUrl:
    content_type = response.header("Content-Type")
    # An External URL or one outside the Scope is checked, never parsed (design D5).
    followed = decision.in_scope and 200 <= response.status_code < 300
    prepared = followed and is_html_type(content_type)
    page = await context.pages.prepare(queued.url, response) if prepared else None
    parsed = page is not None and page.parsed
    # The Link and Refresh headers of an in-Scope 2xx response count, whatever became of its
    # preparation (design D9).
    links = (
        response_links(queued.url, response, context.scope, context.strip_params)
        if followed
        else ()
    )
    if page is not None:
        links += page.document_links
    nofollow = page is not None and page.directives.nofollow
    discovered = discovered_urls(
        links,
        context.scope,
        queued.crawl_depth + 1,
        nofollow=nofollow,
        follow_nofollow=context.settings.follow_nofollow,
    )
    if parsed and queued.discovered_via == "seed":
        _warn_of_seed_base_mismatch(context, queued.url, links)
    parse_error = None if page is None else page.parse_error
    parse_error_message = None if page is None else page.parse_error_message
    if parse_error is not None:
        failure = _parse_failure(queued.url, parse_error, parse_error_message)
        context.reporter.count(Diagnostic.of(PARSE_FAILED, failure), queued.url)
    result = _result(
        queued,
        decision,
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
    return FetchedUrl(
        url_id=queued.id,
        status_code=response.status_code,
        content_type=content_type,
        fetched_at=response.fetched_at,
        response_time_ms=response.response_time_ms,
        parsed=parsed,
        parse_error=parse_error,
        parse_error_message=parse_error_message,
        discovered=discovered,
        rows=_handler_rows(context, result),
    )


def _warn_of_seed_base_mismatch(
    context: CrawlContext, seed: NormalizedUrl, links: Iterable[DiscoveredLink]
) -> None:
    apex_seed = apex_seed_named_by_page(seed, links, context.scope)
    if apex_seed is not None:
        context.reporter.warn(
            Diagnostic.of(
                SEED_BASE_MISMATCH,
                f"The Seed {seed} names its apex host as the site: its Page links there by its "
                "canonical or by most of its hyperlinks, so the Crawl may miss most of the site.",
                hint=f"Give {apex_seed} as the Seed to crawl the site its Page names.",
                details={"seed": seed, "apex_seed": apex_seed},
            )
        )


def _parse_failure(url: NormalizedUrl, parse_error: ParseError, message: str | None) -> str:
    if parse_error == "extractor_error":
        return (
            f"An extractor failed on {url} ({message}); the Page was recorded without its "
            "output, and its Links were followed."
        )
    detail = parse_error if message is None else f"{parse_error}: {message}"
    return (
        f"Preparing {url} gave nothing ({detail}); it was recorded unparsed, with only the "
        "Links of its headers."
    )


def _result(queued: QueuedUrl, decision: ScopeDecision, **outcome: Any) -> UrlResult:
    return UrlResult(
        url_id=queued.id,
        url=queued.url,
        crawl_depth=queued.crawl_depth,
        discovered_via=queued.discovered_via,
        found_on_url_id=queued.found_on_url_id,
        is_internal=decision.is_internal,
        in_scope=decision.in_scope,
        **outcome,
    )


def _handler_rows(context: CrawlContext, result: UrlResult) -> tuple[object, ...]:
    rows: list[object] = []
    for handler in context.hooks.handlers:
        try:
            # Whole, or not at all: a handler that fails midway keeps none of its rows.
            rows.extend(tuple(handler.handle(result)))
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
