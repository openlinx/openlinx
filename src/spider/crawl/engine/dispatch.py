"""The engine: the frontier depth by depth, and each URL's task (020-add-crawl-core D1, D2, D3)."""

import asyncio
from functools import partial

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import warn_of_the_url_limit
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.seed_chain import SeedChain
from spider.crawl.engine.units import Run, close_seed_chain, unit_of, via_resource
from spider.crawl.fetch.politeness import BlockingRuns, RateGate, RequestLimits
from spider.crawl.fetch.requester import Requester
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
    limits = RequestLimits(
        context.settings.concurrency, context.pages.backlog, context.settings.max_urls
    )
    requester = Requester(
        context.fetcher,
        limits,
        RateGate(context.clock, context.settings.rate),
        clock=context.clock,
        retries=context.settings.retries,
    )
    run = Run(
        context=context,
        outcomes=Outcomes(context),
        limits=limits,
        requester=requester,
        robots=RobotsLoader(requester, context.writer, context.settings.robots_user_agent),
        blocking=BlockingRuns(),
        checked_urls=set(),
        seed_chain=SeedChain(context.scope, seed),
    )
    decision = context.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    depth: int | None = 0
    try:
        while depth is not None:
            await _crawl_depth(run, depth)
            if run.seed_chain.is_open and not context.stop.is_set:
                # No URL of the chain was decided, such as one the URL limit refused.
                await close_seed_chain(run, seed, responded=False)
            # A stop cancels the checked URLs in flight: the sweep below would wait for them.
            if context.stop.is_set:
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
        await run.robots.close()
    await run.outcomes.settled()
    limit = limits.limit_reached()
    # Only once every outcome is in: a failure among them outranks the stop.
    if limit is not None and context.stop.reason == "max_urls":
        warn_of_the_url_limit(context, limit)


async def _crawl_depth(run: Run, depth: int) -> None:
    """Returns once every followed URL's task of the depth has ended, so the next depth sees
    their URLs; the depth's checked URLs join the run's and run on."""
    context, limits = run.context, run.limits
    running: set[asyncio.Task[None]] = set()
    try:
        # A pass reads the depth from the top, so it also finds a queued URL that a redirect
        # lowered to it below the last pass's cursor (022 D2). Within a pass the cursor keeps a
        # URL in flight from being read twice (design D1); across passes only the depth's
        # checked URLs are still in flight, bounded by the task cap, and the URLs whose outcome
        # is pending, bounded by the writer's batch.
        checked_in_flight: set[int] = set()
        while True:
            dispatched, after = False, 0
            while limits.limit_reached() is None and (
                batch := await context.writer.run_async(
                    queued_batch(depth, after, _FRONTIER_BATCH, context.settings.max_redirects)
                )
            ):
                for queued in batch:
                    # A URL whose unit failed is still queued until its fallback is in.
                    if queued.id in checked_in_flight or run.outcomes.is_pending(queued.id):
                        continue
                    await limits.reserve_task()
                    if context.stop.is_set:
                        limits.task_ended()
                        return
                    if limits.limit_reached() is not None:
                        limits.task_ended()
                        break
                    in_chain = run.seed_chain.is_open and queued.crawl_depth == 0
                    decision = run.seed_chain.decide(queued.url, in_chain=in_chain)
                    task = asyncio.create_task(_crawl_url(run, queued, decision))
                    # A checked URL never holds the barrier (design D3); the sweep in run_crawl
                    # reads what one finds after its depth has closed.
                    # The chain's last URL closes it before depth 0 ends (022 D3), even a
                    # checked one, such as a URL off the Seed's site or its folder.
                    if _is_checked_url(queued, decision) and not in_chain:
                        run.checked_urls.add(task)
                        task.add_done_callback(run.checked_urls.discard)
                        checked_in_flight.add(queued.id)
                        task.add_done_callback(partial(_discard, checked_in_flight, queued.id))
                    else:
                        running.add(task)
                        task.add_done_callback(running.discard)
                    dispatched = True
                after = batch[-1].id
            if not dispatched:
                return
            await asyncio.gather(*running)
    finally:
        await _cancel_all(running)


async def _cancel_all(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Retrieved, so that no "Task exception was never retrieved" reaches stderr.
    await asyncio.gather(*tasks, return_exceptions=True)


def _is_checked_url(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or via_resource(queued)


def _discard(ids: set[int], url_id: int, _: object) -> None:
    ids.discard(url_id)


async def _crawl_url(run: Run, queued: QueuedUrl, decision: ScopeDecision) -> None:
    try:
        recorded = await unit_of(run, queued, decision)
        # The URL's task ends at the submit; its outcome arrives at the commit (design D2).
        if recorded is not None:
            await run.outcomes.submit(*recorded)
    finally:
        run.limits.task_ended()
