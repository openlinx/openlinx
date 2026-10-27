"""The engine: the frontier depth by depth, and each URL's task (020-add-crawl-core D1, D2, D3)."""

import asyncio

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import url_limit_reached
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.pause import NetworkPause
from spider.crawl.engine.units import Run, TaskFailure, unit_of, via_resource
from spider.crawl.fetch.fetcher import REQUEST_DEADLINE_SECONDS
from spider.crawl.fetch.politeness import BlockingRuns, RateGate, RequestLimits, global_cap
from spider.crawl.fetch.requester import Requester, watchdog_seconds
from spider.crawl.pages.preparation import PageSettings
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.scope import ScopeDecision
from spider.crawl.urls import NormalizedUrl
from spider.store.records import QueuedUrl
from spider.store.urls import next_depth, queued_batch, record_seed
from spider.store.writer import CrawlWriterClosedError

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100
# next_depth gives the smallest queued depth above it, so above this one, any depth.
_ABOVE_NO_DEPTH = -1


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    concurrency = context.settings.concurrency
    cap = global_cap(concurrency)
    limits = RequestLimits(cap, context.pages.backlog, context.settings.max_urls)
    gate = RateGate(context.clock, context.settings.rate)
    requester = Requester(
        context.fetcher,
        limits,
        gate,
        concurrency=concurrency,
        cap=cap,
        clock=context.clock,
        watchdog_seconds=watchdog_seconds(REQUEST_DEADLINE_SECONDS),
        stopped=lambda: context.stop.is_set,
    )
    run = Run(
        context=context,
        outcomes=Outcomes(context.writer, context.reporter, context.stop),
        limits=limits,
        requester=requester,
        robots=RobotsLoader(requester, context.writer, context.settings.robots_user_agent),
        blocking=BlockingRuns(),
        checked_urls=set(),
        task_failure=TaskFailure(context.stop),
        pause=NetworkPause(
            concurrency=concurrency,
            network_wait=context.settings.network_wait,
            seed=seed,
            stop=context.stop,
            requester=requester,
            clock=context.clock,
            log=context.reporter,
        ),
    )
    decision = context.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    # Once, with the final Scope: 022 moves this to the end of the Seed's Redirect Chain.
    await context.pages.start(
        PageSettings(
            scope=context.scope,
            extractors=context.hooks.extractors,
            robots_token=context.settings.robots_user_agent,
            follow_nofollow=context.settings.follow_nofollow,
            strip_params=context.strip_params,
        )
    )
    depth: int | None = 0
    try:
        while depth is not None:
            await _crawl_depth(run, depth)
            # A stop or a bug cancels the checked URLs in flight: the sweep below would wait for
            # them.
            if context.stop.is_set or run.task_failure.is_set:
                break
            if limits.limit_reached() is not None:
                # The URL limit: what has started ends and is recorded, and nothing more starts.
                await asyncio.gather(*run.checked_urls)
                context.stop.set("max_urls")
                break
            # Read after every unit submitted so far, so it sees the URLs they discovered.
            depth = await context.writer.run_async(next_depth(depth))
            if depth is None:
                # A checked URL that was in-Scope HTML may have found URLs, or a shorter path
                # to them, at a depth the frontier has passed: once every checked URL has ended,
                # and every outcome, so that no URL whose unit failed is still queued, the queue
                # is read from the top.
                await asyncio.gather(*run.checked_urls)
                await run.outcomes.settled()
                depth = await context.writer.run_async(next_depth(_ABOVE_NO_DEPTH))
    # An ended writer refuses every unit; its cause says why it ended (017 D6).
    except CrawlWriterClosedError as closed:
        context.stop.set("write_failed", closed.__cause__ or closed)
    finally:
        await _cancel_all(run.checked_urls)
        await run.pause.close()
        await run.robots.close()
    # Once every task has ended, including those that the cancellation above ended.
    run.task_failure.raise_first()
    await run.outcomes.settled()
    limit = limits.limit_reached()
    # Only once every outcome is in: a failure among them outranks the stop.
    if limit is not None and context.stop.reason == "max_urls":
        context.reporter.warn(url_limit_reached(context.crawl_file.id, limit))


async def _crawl_depth(run: Run, depth: int) -> None:
    """Returns once every followed URL's task of the depth has ended, so the next depth sees
    their URLs; the depth's checked URLs join the run's and run on."""
    context, limits = run.context, run.limits
    running: set[asyncio.Task[None]] = set()
    try:
        # The cursor of this run: a URL in flight is never read twice (design D1).
        after = 0
        while limits.limit_reached() is None and (
            batch := await context.writer.run_async(queued_batch(depth, after, _FRONTIER_BATCH))
        ):
            for queued in batch:
                await limits.reserve_task()
                if context.stop.is_set or run.task_failure.is_set:
                    limits.task_ended()
                    return
                if limits.limit_reached() is not None:
                    limits.task_ended()
                    break
                decision = context.scope.decide(queued.url)
                task = asyncio.create_task(_crawl_url(run, queued, decision))
                # A checked URL never holds the barrier (design D3); the sweep in run_crawl reads
                # what one finds after its depth has closed.
                tasks = run.checked_urls if _is_checked_url(queued, decision) else running
                run.task_failure.track(tasks, task)
            after = batch[-1].id
        if running:
            await asyncio.gather(*running)
    finally:
        await _cancel_all(running)


async def _cancel_all(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Only cancellation is swallowed here: any other exception has reached the run's
    # TaskFailure through its task's done callback.
    await asyncio.gather(*tasks, return_exceptions=True)


def _is_checked_url(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or via_resource(queued)


async def _crawl_url(run: Run, queued: QueuedUrl, decision: ScopeDecision) -> None:
    try:
        recorded = await unit_of(run, queued, decision)
        # The URL's task ends at the submit; its outcome arrives at the commit (design D2).
        if recorded is not None:
            await run.outcomes.submit(recorded)
    finally:
        run.limits.task_ended()
