"""The engine: the frontier depth by depth, and each URL's task (020-add-crawl-core D1, D2, D3)."""

import asyncio
from collections.abc import Sequence
from typing import Literal

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import url_limit_reached
from spider.crawl.engine.outcomes import Outcomes
from spider.crawl.engine.pause import CountedUrl, NetworkPause, PauseEnd, Redispatch
from spider.crawl.engine.progress import UrlCounters, report_progress
from spider.crawl.engine.stop import StopGrace
from spider.crawl.engine.units import Run, TaskFailure, unit_of, via_resource
from spider.crawl.fetch.fetcher import REQUEST_DEADLINE_SECONDS
from spider.crawl.fetch.politeness import BlockingRuns, RateGate, RequestLimits, global_cap
from spider.crawl.fetch.requester import Requester, watchdog_seconds
from spider.crawl.pages.preparation import PageSettings
from spider.crawl.robots.loader import RobotsLoader
from spider.crawl.scope import ScopeDecision
from spider.crawl.urls import NormalizedUrl
from spider.store.records import QueuedUrl
from spider.store.urls import next_depth, queued_batch, record_seed, requeue, url_counts
from spider.store.writer import CrawlWriterClosedError

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100
# next_depth gives the smallest queued depth above it, so above this one, any depth.
_ABOVE_NO_DEPTH = -1
# Clock seconds that the requests in flight at a stop may still take (design D16).
STOP_GRACE_SECONDS = 10


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
    redispatch = Redispatch()
    robots = RobotsLoader(requester, context.writer, context.settings.robots_user_agent)
    task_failure = TaskFailure(context.stop)
    # The tasks that run beside the URLs' own: the network pause's probing, the progress events.
    side_tasks: set[asyncio.Task[None]] = set()
    decision = context.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    # Once a run, so a continued Crawl starts from the file's counts (design D10).
    counters = UrlCounters(await context.writer.run_async(url_counts()))

    async def resumed(end: PauseEnd, count: Sequence[CountedUrl]) -> None:
        if end != "outage":
            return
        # The network was down, not the site: robots.txt is asked again (design D16).
        robots.forget_unanswered(lambda url: context.scope.decide(url).is_internal)
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
        stop=context.stop,
        requester=requester,
        clock=context.clock,
        log=context.reporter,
        resumed=resumed,
        track=lambda task: task_failure.track(side_tasks, task),
    )
    run = Run(
        context=context,
        outcomes=Outcomes(context.writer, context.reporter, context.stop, counters),
        limits=limits,
        requester=requester,
        robots=robots,
        blocking=BlockingRuns(),
        checked_urls=set(),
        task_failure=task_failure,
        pause=pause,
        redispatch=redispatch,
        grace=StopGrace(context.clock, STOP_GRACE_SECONDS),
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
    progress = asyncio.create_task(
        report_progress(
            clock=context.clock,
            log=context.reporter,
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
            # The checked URLs in flight get the grace too; the sweep below would wait for them.
            if _stopping(run):
                await _wait_out(run, run.checked_urls)
                break
            # Read after every unit submitted so far, so it sees the URLs they discovered.
            depth = await context.writer.run_async(next_depth(depth))
            if depth is None:
                # A checked URL that was in-Scope HTML may have found URLs, or a shorter path
                # to them, at a depth the frontier has passed: once every checked URL has ended,
                # and every outcome, so that no URL whose unit failed is still queued, the queue
                # is read from the top.
                await _wait_out(run, run.checked_urls)
                if _stopping(run):
                    break
                await run.outcomes.settled()
                depth = await context.writer.run_async(next_depth(_ABOVE_NO_DEPTH))
                while depth is None and run.pause.paused:
                    # Nothing is left to request, but a pause may end in an outage, which
                    # re-queues the URLs of its count.
                    await run.pause.ended()
                    depth = await context.writer.run_async(next_depth(_ABOVE_NO_DEPTH))
    # An ended writer refuses every unit; its cause says why it ended (017 D6).
    except CrawlWriterClosedError as closed:
        context.stop.set("write_failed", closed.__cause__ or closed)
    finally:
        await _cancel_all(run.checked_urls)
        await run.pause.close()
        await _cancel_all(side_tasks)
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
    their URLs, or after a stop's grace; the depth's checked URLs join the run's and run on."""
    running: set[asyncio.Task[None]] = set()
    try:
        await _start_depth(run, depth, running)
        if run.limits.limit_reached() is not None:
            # The URL limit is a stop: what has started gets the grace, and nothing more starts.
            run.context.stop.set("max_urls")
        await _wait_out(run, running)
    finally:
        await _cancel_all(running)


async def _start_depth(run: Run, depth: int, running: set[asyncio.Task[None]]) -> None:
    """Starts the depth's followed URLs until none is left, the URL limit refuses one, or the
    Crawl stops."""
    context, limits = run.context, run.limits
    # The cursor of this run: a URL in flight is never read twice (design D1).
    after = 0
    while limits.limit_reached() is None:
        started = await _start_again(run, running)
        if started == "stopped":
            return
        batch = await context.writer.run_async(queued_batch(depth, after, _FRONTIER_BATCH))
        if started == "limit" or not batch:
            return
        for queued in batch:
            if not run.redispatch.claim(queued.id):
                continue
            started = await _start_again(run, running)
            if started == "go_on":
                started = await _start(run, queued, running)
            if started != "go_on":
                return
        after = batch[-1].id


async def _wait_out(run: Run, tasks: set[asyncio.Task[None]]) -> None:
    """Waits until the tasks have ended; once the Crawl stops, for STOP_GRACE_SECONDS of clock
    time at most, and a bug ends the wait at once. The caller cancels what is left, before its
    submit, so its URL stays queued (design D16)."""
    stop, failure = run.context.stop, run.task_failure
    stopped = asyncio.ensure_future(stop.wait())
    try:
        while tasks and not stop.is_set and not failure.is_set:
            await asyncio.wait({*tasks, stopped}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopped.cancel()
        await asyncio.wait({stopped})
    if not tasks or failure.is_set:
        return
    grace = asyncio.ensure_future(run.context.clock.sleep(run.grace.remaining()))
    try:
        while tasks and not grace.done() and not failure.is_set:
            await asyncio.wait({*tasks, grace}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        grace.cancel()
        await asyncio.wait({grace})


type _Started = Literal["go_on", "stopped", "limit"]


async def _start_again(run: Run, running: set[asyncio.Task[None]]) -> _Started:
    """Dispatches what a network pause re-queued or left queued, ahead of the frontier read,
    each at the depth it was found at (design D3)."""
    urls = run.redispatch.take()
    for index, queued in enumerate(urls):
        started = await _start(run, queued, running)
        if started != "go_on":
            run.redispatch.put_back(urls[index:])
            return started
    return "go_on"


async def _start(run: Run, queued: QueuedUrl, running: set[asyncio.Task[None]]) -> _Started:
    context, limits = run.context, run.limits
    await limits.reserve_task()
    if context.stop.is_set or run.task_failure.is_set:
        limits.task_ended()
        return "stopped"
    if limits.limit_reached() is not None:
        limits.task_ended()
        return "limit"
    decision = context.scope.decide(queued.url)
    task = asyncio.create_task(_crawl_url(run, queued, decision))
    # A checked URL never holds the barrier (design D3); the sweep in run_crawl reads what one
    # finds after its depth has closed.
    tasks = run.checked_urls if _is_checked_url(queued, decision) else running
    run.task_failure.track(tasks, task)
    return "go_on"


async def _cancel_all(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Only cancellation is swallowed here: any other exception has reached the run's
    # TaskFailure through its task's done callback.
    await asyncio.gather(*tasks, return_exceptions=True)


def _stopping(run: Run) -> bool:
    return run.context.stop.is_set or run.task_failure.is_set


def _is_checked_url(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or via_resource(queued)


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
