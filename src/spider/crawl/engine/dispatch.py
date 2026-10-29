"""The engine: the frontier depth by depth, and each URL's task (020-add-crawl-core D1, D2, D3)."""

import asyncio
from collections.abc import Sequence
from functools import partial
from typing import Literal

from spider.aio import first_of
from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import url_limit_reached
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.pause import CountedUrl, NetworkPause, PauseEnd, Redispatch
from spider.crawl.engine.progress import UrlCounters, report_progress
from spider.crawl.engine.seed_chain import SeedChain, close_seed_chain
from spider.crawl.engine.stop import StopGrace
from spider.crawl.engine.tasks import Run, TaskFailure
from spider.crawl.engine.units import unit_of, via_resource
from spider.crawl.fetch.politeness import BlockingRuns, RateGate, RequestLimits, global_cap
from spider.crawl.fetch.requester import Requester, watchdog_seconds
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.scope import ScopeDecision
from spider.crawl.urls import NormalizedUrl
from spider.store.records import QueuedUrl
from spider.store.urls import (
    next_depth,
    queued_batch,
    record_seed,
    requeue,
    seed_answered,
    url_counts,
)
from spider.store.writer import CrawlWriterClosedError

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100
# next_depth gives the smallest queued depth above it, so above this one, any depth.
_ABOVE_NO_DEPTH = -1
# Clock seconds that the requests in flight at a stop may still take (design D16).
STOP_GRACE_SECONDS = 10


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    seed_chain = SeedChain(context.planned_scope, seed)
    decision = seed_chain.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    # Once a run, so a continued Crawl starts from the file's counts (design D10).
    counts = await context.writer.run_async(url_counts())
    counters = UrlCounters(counts)
    concurrency = context.settings.concurrency
    cap = global_cap(concurrency)
    # The URLs a continued Crawl fetched before count toward its limit (design D20).
    limits = RequestLimits(
        cap, context.pages.backlog, context.settings.max_urls, started=counts.fetched
    )
    gate = RateGate(context.clock, context.settings.rate)
    requester = Requester(
        context.fetcher,
        limits,
        gate,
        concurrency=concurrency,
        cap=cap,
        clock=context.clock,
        retries=context.settings.retries,
        # The Fetcher's own deadline is the timeout setting, as its policy takes it.
        watchdog_seconds=watchdog_seconds(context.settings.timeout),
        stop=context.stop,
    )
    redispatch = Redispatch()
    robots = RobotsLoader(requester, context.writer, context.settings.robots_user_agent)
    task_failure = TaskFailure(context.stop)
    # The tasks that run beside the URLs' own: the network pause's probing, the progress events.
    side_tasks: set[asyncio.Task[None]] = set()

    async def resumed(end: PauseEnd, count: Sequence[CountedUrl]) -> None:
        if end != "outage":
            return
        # The network was down, not the site: robots.txt is asked again (design D16).
        robots.forget_unanswered(lambda url: seed_chain.scope.decide(url).is_internal)
        requeued = redispatch.requeue(count)
        # Each whose own request counted toward the URL limit counts again when it is requested.
        for counted in requeued:
            if counted.requested:
                requester.give_back()
        ids = [counted.queued.id for counted in requeued]
        counters.add(await context.writer.run_async(requeue(ids)))

    pause = NetworkPause(
        concurrency=concurrency,
        network_wait=context.settings.network_wait,
        seed=seed,
        crawl_id=context.crawl_file.id,
        seed_answered=await context.writer.run_async(seed_answered(seed)),
        stop=context.stop,
        requester=requester,
        clock=context.clock,
        warnings=context.warnings,
        resumed=resumed,
        track=lambda task: task_failure.track(side_tasks, task),
    )
    run = Run(
        context=context,
        outcomes=Outcomes(context.writer, context.warnings, context.stop, counters),
        limits=limits,
        requester=requester,
        robots=robots,
        blocking=BlockingRuns(),
        seed_chain=seed_chain,
        task_failure=task_failure,
        pause=pause,
        redispatch=redispatch,
        grace=StopGrace(context.clock, STOP_GRACE_SECONDS),
    )
    context.stop.on_first_set(lambda _reason: run.grace.start())
    progress = asyncio.create_task(
        report_progress(
            clock=context.clock,
            warnings=context.warnings,
            crawl_id=context.crawl_file.id,
            counters=counters,
            rate=requester.rate,
            paused=lambda: pause.paused,
        )
    )
    task_failure.track(side_tasks, progress)
    depth: int | None = 0
    try:
        while depth is not None:
            await _crawl_depth(run, depth)
            if run.seed_chain.is_open and _closes_the_seed_chain(run):
                # No URL of the chain was decided, such as one the URL limit refused.
                await close_seed_chain(context, run.seed_chain, responded=False)
            # The checked URLs in flight get the grace too; the sweep below would wait for them.
            if _stopping(run):
                await _wait_out(run, run.task_failure.checked_urls)
                break
            # Read after every unit submitted so far, so it sees the URLs they discovered.
            depth = await context.writer.run_async(next_depth(depth))
            if depth is None:
                # A checked URL that was in-Scope HTML may have found URLs, or a shorter path
                # to them, at a depth the frontier has passed: once every checked URL has ended,
                # and every outcome, so that no URL whose unit failed is still queued, the queue
                # is read from the top.
                await _wait_out(run, run.task_failure.checked_urls)
                if _stopping(run):
                    break
                await run.outcomes.settled()
                depth = await context.writer.run_async(next_depth(_ABOVE_NO_DEPTH))
                while depth is None and run.pause.paused:
                    # Nothing is left to request, but a pause may end in an outage, which
                    # re-queues the URLs of its count.
                    await run.pause.ended()
                    depth = await context.writer.run_async(next_depth(_ABOVE_NO_DEPTH))
    # An ended writer refuses every unit.
    except CrawlWriterClosedError as closed:
        context.stop.write_failed(closed)
    finally:
        await _cancel_all(run.task_failure.checked_urls)
        await run.pause.close()
        await _cancel_all(side_tasks)
        await run.robots.close()
    # Once every task has ended, including those that the cancellation above ended.
    run.task_failure.raise_first()
    await run.outcomes.settled()
    limit = limits.limit_reached()
    # Only once every outcome is in: a failure among them outranks the stop.
    if limit is not None and context.stop.reason == "max_urls":
        context.warnings.warn(url_limit_reached(context.crawl_file.id, limit))


async def _crawl_depth(run: Run, depth: int) -> None:
    """Returns once every followed URL's task of the depth has ended, so the next depth sees
    their URLs, or after a stop's grace; the depth's checked URLs join the run's and run on."""
    running: set[asyncio.Task[None]] = set()
    try:
        # A pass reads the depth from the top, so it also finds a queued URL that a redirect
        # lowered to it below the last pass's cursor (022 D2). Within a pass the cursor keeps a
        # URL in flight from being read twice (design D1); across passes only the depth's
        # checked URLs are still in flight, bounded by the task cap, and the URLs whose outcome
        # is pending, bounded by the writer's batch.
        checked_in_flight: set[int] = set()
        while True:
            dispatched = await _start_depth(run, depth, running, checked_in_flight)
            if run.limits.limit_reached() is not None:
                # The URL limit is a stop: what has started gets the grace, and nothing more
                # starts.
                run.context.stop.set("max_urls")
            await _wait_out(run, running)
            if not dispatched or _stopping(run):
                return
    finally:
        await _cancel_all(running)


async def _start_depth(
    run: Run, depth: int, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> bool:
    """Starts the depth's followed URLs until none is left, the URL limit refuses one, or the
    Crawl stops; whether it started any."""
    context, limits = run.context, run.limits
    dispatched = False
    # The cursor of this pass: a URL in flight is never read twice (design D1).
    after = 0
    while limits.limit_reached() is None:
        started = await _start_again(run, running, checked_in_flight)
        if started == "stopped":
            return dispatched
        batch = await context.writer.run_async(
            queued_batch(depth, after, _FRONTIER_BATCH, context.settings.max_redirects)
        )
        if started == "limit" or not batch:
            return dispatched
        for queued in batch:
            # A URL whose unit failed is still queued until its fallback is in.
            if queued.id in checked_in_flight or run.outcomes.is_pending(queued.id):
                continue
            if not run.redispatch.claim(queued.id):
                continue
            started = await _start_again(run, running, checked_in_flight)
            if started == "go_on":
                started = await _start(run, queued, running, checked_in_flight)
                dispatched = True
            if started != "go_on":
                return dispatched
        after = batch[-1].id
    return dispatched


async def _wait_out(run: Run, tasks: set[asyncio.Task[None]]) -> None:
    """Waits until the tasks have ended; once the Crawl stops, for STOP_GRACE_SECONDS of clock
    time at most, and a bug ends the wait at once. The caller cancels what is left, before its
    submit, so its URL stays queued (design D16)."""
    stop, failure = run.context.stop, run.task_failure
    while tasks and not stop.is_set and not failure.is_set:
        await first_of(stop.wait(), wake_on=tasks)
    if not tasks or failure.is_set:
        return
    while tasks and not failure.is_set:
        grace = await first_of(run.context.clock.sleep(run.grace.remaining()), wake_on=tasks)
        if not grace.cancelled():
            break


type _Started = Literal["go_on", "stopped", "limit"]


async def _start_again(
    run: Run, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> _Started:
    """Dispatches what a network pause re-queued or left queued, ahead of the frontier read,
    each at the depth it was found at (design D3)."""
    urls = run.redispatch.take()
    for index, queued in enumerate(urls):
        started = await _start(run, queued, running, checked_in_flight)
        if started != "go_on":
            run.redispatch.put_back(urls[index:])
            return started
    return "go_on"


async def _start(
    run: Run, queued: QueuedUrl, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> _Started:
    context, limits = run.context, run.limits
    if not await _reserve_task(run):
        return "stopped"
    if context.stop.is_set or run.task_failure.is_set:
        limits.task_ended()
        return "stopped"
    if limits.limit_reached() is not None:
        limits.task_ended()
        return "limit"
    in_chain = run.seed_chain.holds(queued)
    decision = run.seed_chain.decide(queued.url, in_chain=in_chain)
    task = asyncio.create_task(_crawl_url(run, queued, decision))
    # A checked URL never holds the barrier (design D3); the sweep in run_crawl reads what one
    # finds after its depth has closed. The chain's last URL closes it before depth 0 ends
    # (022 D3), even a checked one, such as a URL off the Seed's site or its folder.
    if _is_checked_url(queued, decision) and not in_chain:
        run.task_failure.track(run.task_failure.checked_urls, task)
        checked_in_flight.add(queued.id)
        task.add_done_callback(partial(_discard, checked_in_flight, queued.id))
    else:
        run.task_failure.track(running, task)
    return "go_on"


async def _reserve_task(run: Run) -> bool:
    """Room for a URL's task, or False once the Crawl stops: the tasks that fill the bound may
    wait for a host's slot that a hanging request holds, and the grace must not wait for it
    (design D16)."""
    reserved = await first_of(run.limits.reserve_task(), run.context.stop.wait())
    return not reserved.cancelled()


async def _cancel_all(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Only cancellation is swallowed here: any other exception has reached the run's
    # TaskFailure through its task's done callback.
    await asyncio.gather(*tasks, return_exceptions=True)


def _stopping(run: Run) -> bool:
    return run.context.stop.is_set or run.task_failure.is_set


def _closes_the_seed_chain(run: Run) -> bool:
    # The URL limit is a stop that leaves the file whole, so the chain's URLs are still decided
    # against the Scope it ended in (022 D3); any other stop or a bug ends the run as it is.
    stop = run.context.stop
    return not run.task_failure.is_set and (not stop.is_set or stop.reason == "max_urls")


def _is_checked_url(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or via_resource(queued)


def _discard(ids: set[int], url_id: int, _: object) -> None:
    ids.discard(url_id)


async def _crawl_url(run: Run, queued: QueuedUrl, decision: ScopeDecision) -> None:
    try:
        recorded = await unit_of(run, queued, decision)
        # The URL's task ends at the submit; its outcome arrives at the commit (design D2).
        if recorded is not None:
            await run.outcomes.submit(recorded)
        else:
            # Still queued: one the re-dispatch list owns waits there, since no frontier read
            # dispatches it again (design D16).
            run.redispatch.put_back([queued])
    finally:
        run.limits.task_ended()
