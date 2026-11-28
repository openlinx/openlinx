"""Dispatch the Crawl frontier by depth and coordinate each URL's task."""

import asyncio
from collections.abc import Sequence
from functools import partial
from typing import Literal

from openlinx.aio import first_of
from openlinx.crawl.engine.blocking import BlockingRuns
from openlinx.crawl.engine.context import CrawlContext
from openlinx.crawl.engine.crawl_warnings import url_limit_reached
from openlinx.crawl.engine.http_versions import HttpVersions
from openlinx.crawl.engine.outcomes import Outcomes
from openlinx.crawl.engine.pause import CountedUrl, NetworkPause, PauseEnd, Redispatch
from openlinx.crawl.engine.progress import UrlCounters, report_progress
from openlinx.crawl.engine.seed_chain import SeedChain, end_seed_chain
from openlinx.crawl.engine.stop import StopGrace
from openlinx.crawl.engine.tasks import Run, TaskFailure
from openlinx.crawl.engine.units import unit_of, via_resource
from openlinx.crawl.fetch.fetcher import ProbesHttpVersion
from openlinx.crawl.fetch.politeness import RateGate, RequestLimits, global_cap
from openlinx.crawl.fetch.requester import Requester, watchdog_seconds
from openlinx.crawl.robots.loader import RobotsLoader
from openlinx.crawl.scope import ScopeDecision
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.origins import init_http_version_claims
from openlinx.store.records import QueuedUrl
from openlinx.store.urls import (
    next_depth,
    queued_batch,
    record_seed,
    requeue,
    seed_answered,
    url_counts,
)
from openlinx.store.writer import CrawlWriterClosedError

# Queued URLs read from the frontier at once.
_FRONTIER_BATCH = 100
# next_depth gives the smallest queued depth above it, so above this one, any depth.
_ABOVE_NO_DEPTH = -1
# Clock seconds that the requests in flight at a stop may still take.
STOP_GRACE_SECONDS = 10

type _Started = Literal["go_on", "stopped", "limit", "host_full"]


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    seed_chain = SeedChain(context.planned_scope, seed)
    decision = seed_chain.scope.decide(seed)
    await context.writer.run_async(
        record_seed(seed, is_internal=decision.is_internal, in_scope=decision.in_scope)
    )
    # Once a run, so a continued Crawl starts from the file's counts.
    counts = await context.writer.run_async(url_counts())
    counters = UrlCounters(counts)
    concurrency = context.settings.concurrency
    cap = global_cap(concurrency)
    # The URLs a continued Crawl fetched before count toward its limit.
    limits = RequestLimits(
        concurrency, context.pages.backlog, context.settings.max_urls, started=counts.fetched
    )
    gate = RateGate(context.clock, context.settings.rate)

    fetcher = context.fetcher
    measure = fetcher.probe_http_version if isinstance(fetcher, ProbesHttpVersion) else None
    http_versions = HttpVersions(context.writer, context.fetch_policy, context.clock, measure)
    await context.writer.run_async(init_http_version_claims)

    requester = Requester(
        context.fetcher,
        limits,
        gate,
        concurrency=concurrency,
        cap=cap,
        clock=context.clock,
        retries=context.settings.retries,
        watchdog_seconds=watchdog_seconds(context.fetch_policy.timeout_seconds),
        stop=context.stop,
        secrets=context.secrets,
        on_request_start=http_versions.requested,
    )
    redispatch = Redispatch()
    robots = RobotsLoader(
        requester,
        context.writer,
        context.settings.robots_user_agent,
        lambda url: seed_chain.decide(url, in_chain=seed_chain.is_open).is_internal,
    )
    task_failure = TaskFailure(context.stop)
    # Work beside the URL tasks: the network pause, progress and origin measurements.
    side_tasks: set[asyncio.Task[None]] = set()

    async def resumed(end: PauseEnd, count: Sequence[CountedUrl]) -> None:
        if end != "outage":
            return
        # The network was down, not the site: robots.txt is asked again.
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
        is_internal=lambda url: seed_chain.scope.decide(url).is_internal,
        crawl_id=context.crawl_file.id,
        seed_answered=await context.writer.run_async(seed_answered(seed)),
        stop=context.stop,
        requester=requester,
        redispatch=redispatch,
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
    measurements = None
    if measure is not None:
        measurements = asyncio.create_task(http_versions.run(requester))
        task_failure.track(side_tasks, measurements)
        context.stop.on_first_set(lambda _: measurements.cancel())
    depth: int | None = 0
    try:
        while depth is not None:
            await _crawl_depth(run, depth)
            if run.seed_chain.is_open and _closes_the_seed_chain(run):
                # Keep the existing Scope when the chain has no terminal outcome this run,
                # for example when the URL limit refused its last request.
                await end_seed_chain(context, run.seed_chain, responded=False)
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
        if measurements is not None and not _stopping(run):
            http_versions.finish()
            await asyncio.wait({measurements})
    # An ended writer refuses every unit.
    except CrawlWriterClosedError as closed:
        context.stop.write_failed(closed)
    finally:
        await _cancel_all(run.task_failure.checked_urls)
        await run.pause.close()
        # The stop callback may already have cancelled the worker. A second cancellation
        # would interrupt its wait for the probe's own cleanup.
        if measurements is not None and measurements.cancelling():
            await asyncio.wait({measurements})
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
        # lowered to it below the last pass's cursor. Within a pass the cursor avoids duplicate
        # reads. Across passes the task cap bounds in-flight Checked URLs, and the writer's
        # submission window bounds units awaiting commit. The pending-outcome check also keeps
        # a URL whose unit failed from being dispatched while its fallback is pending.
        checked_in_flight: set[int] = set()
        while True:
            dispatched = await _start_depth(run, depth, running, checked_in_flight)
            if run.limits.limit_reached() is not None:
                await _wait_for_the_pause_count(run, running)
                # Read again: counts given back meanwhile take the refusal back.
                if run.limits.limit_reached() is not None:
                    # The URL limit is a stop: what has started gets the grace, and nothing more
                    # starts.
                    run.context.stop.set("max_urls")
                else:
                    # The URLs it refused are queued at this depth: another pass reads them.
                    dispatched = True
            if not _stopping(run) and not await _ended_or_refused(run, running):
                continue
            await _wait_out(run, running)
            if not dispatched or _stopping(run):
                return
    finally:
        await _cancel_all(running)


async def _start_depth(
    run: Run, depth: int, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> bool:
    """Dispatches this depth's queued URLs, checks included, until the frontier runs out, the
    URL limit refuses a request or the Crawl stops. Reports whether it attempted a dispatch
    from the frontier in this pass."""
    context, limits = run.context, run.limits
    dispatched = False
    # The cursor of this pass: a URL in flight is never read twice.
    after = 0
    while limits.limit_reached() is None:
        task_ended = limits.watch_task_ends()
        started = await _start_again(run, running, checked_in_flight)
        if started in {"stopped", "limit"}:
            return dispatched
        batch = await context.writer.run_async(
            queued_batch(depth, after, _FRONTIER_BATCH, context.settings.max_redirects)
        )
        if not batch:
            if started == "host_full" and await _wait_for_task_end(run, task_ended):
                continue
            return dispatched
        after = batch[-1].id
        started, attempted = await _start_batch(run, batch, running, checked_in_flight)
        dispatched |= attempted
        if started != "go_on":
            return dispatched
    return dispatched


async def _start_batch(
    run: Run,
    batch: Sequence[QueuedUrl],
    running: set[asyncio.Task[None]],
    checked_in_flight: set[int],
) -> tuple[_Started, bool]:
    dispatched = False
    while batch:
        task_ended = run.limits.watch_task_ends()
        deferred: list[QueuedUrl] = []
        for queued in batch:
            # A URL whose unit failed is still queued until its fallback is in.
            if queued.id in checked_in_flight or run.outcomes.is_pending(queued.id):
                continue
            if not run.redispatch.claim(queued.id):
                continue
            started = await _start_again(run, running, checked_in_flight)
            if started in {"stopped", "limit"}:
                return started, dispatched
            started = await _start(run, queued, running, checked_in_flight)
            if started == "host_full":
                # Keep only this batch in memory. A saturated host leaves room for
                # other hosts in the batch to start before the dispatcher waits.
                deferred.append(queued)
                continue
            dispatched = True
            if started != "go_on":
                return started, dispatched
        if deferred and not await _wait_for_task_end(run, task_ended):
            return "stopped", dispatched
        batch = deferred
    return "go_on", dispatched


async def _wait_for_task_end(run: Run, task_ended: asyncio.Event) -> bool:
    await first_of(task_ended.wait(), run.context.stop.wait(), run.limits.refused())
    return not _stopping(run) and run.limits.limit_reached() is None


async def _wait_for_the_pause_count(run: Run, running: set[asyncio.Task[None]]) -> None:
    """A refusal at the URL limit while the network pause's count is open waits for its
    verdict, since an outage, or a failure while paused, gives counts back and takes the
    refusal back: while the depth's requests end, then for a pause that is on, for
    --network-wait from the refusal at most (022-add-fetch-policy D4)."""
    pause, clock = run.pause, run.context.clock
    ends = clock.monotonic() + run.context.settings.network_wait
    while pause.counting and not _stopping(run):
        requests = running | run.task_failure.internal_checked_urls
        if not requests:
            break
        left = ends - clock.monotonic()
        if left <= 0:
            return
        await first_of(run.context.stop.wait(), clock.sleep(left), wake_on=requests)
    left = ends - clock.monotonic()
    if pause.paused and not _stopping(run) and left > 0:
        await first_of(pause.ended(), clock.sleep(left))


async def _ended_or_refused(run: Run, tasks: set[asyncio.Task[None]]) -> bool:
    """Waits until the tasks have ended or the Crawl stops; False as soon as the URL limit
    refuses a URL inside one of them, so the depth's loop decides the refusal at once, wherever
    it was waiting."""
    limits, stop, failure = run.limits, run.context.stop, run.task_failure
    while tasks and not stop.is_set and not failure.is_set:
        if limits.limit_reached() is not None:
            return False
        await first_of(stop.wait(), limits.refused(), wake_on=tasks)
    return True


async def _wait_out(run: Run, tasks: set[asyncio.Task[None]]) -> None:
    """Waits until the tasks have ended; once the Crawl stops, for STOP_GRACE_SECONDS of clock
    time at most, and a bug ends the wait at once. The caller cancels what is left, before its
    submit, so its URL stays queued (020-add-crawl-core D16)."""
    stop, failure = run.context.stop, run.task_failure
    while tasks and not stop.is_set and not failure.is_set:
        await first_of(stop.wait(), wake_on=tasks)
    if not tasks or failure.is_set:
        return
    while tasks and not failure.is_set:
        grace = await first_of(run.context.clock.sleep(run.grace.remaining()), wake_on=tasks)
        if not grace.cancelled():
            break


async def _start_again(
    run: Run, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> _Started:
    """Dispatches what a network pause re-queued or left queued at its original depth.
    Saturated hosts stay on the redispatch list while other hosts can start."""
    urls = run.redispatch.take()
    result: _Started = "go_on"
    for index, queued in enumerate(urls):
        started = await _start(run, queued, running, checked_in_flight)
        if started == "host_full":
            run.redispatch.put_back((queued,))
            result = started
        elif started != "go_on":
            run.redispatch.put_back(urls[index:])
            return started
    return result


async def _start(
    run: Run, queued: QueuedUrl, running: set[asyncio.Task[None]], checked_in_flight: set[int]
) -> _Started:
    limits = run.limits
    if _stopping(run):
        return "stopped"
    host = limits.task_host(queued.url)
    if limits.host_full(host):
        return "host_full"
    if not await _reserve_task(run, host):
        return "stopped"
    if _stopping(run):
        limits.task_ended(host)
        return "stopped"
    if limits.limit_reached() is not None:
        limits.task_ended(host)
        return "limit"
    in_chain = run.seed_chain.holds(queued)
    decision = run.seed_chain.decide(queued.url, in_chain=in_chain)
    task = asyncio.create_task(_crawl_url(run, queued, decision))
    # A cancellation before the coroutine first runs must also return its capacity.
    task.add_done_callback(lambda _: limits.task_ended(host))
    # A checked URL never holds the barrier; the sweep in run_crawl reads what one
    # finds after its depth has closed. The chain's last URL closes it before depth 0 ends,
    # even a checked one, such as a URL off the Seed's site or its folder.
    if _is_checked_url(queued, decision) and not in_chain:
        run.task_failure.track(
            run.task_failure.checked_urls, task, internal_checked=decision.is_internal
        )
        checked_in_flight.add(queued.id)
        task.add_done_callback(partial(_discard, checked_in_flight, queued.id))
    else:
        run.task_failure.track(running, task)
    return "go_on"


async def _reserve_task(run: Run, host: str | None) -> bool:
    """Room for a URL's task, or False once the Crawl stops: the tasks that fill the bound may
    wait for a host's slot that a hanging request holds, and the grace must not wait for it."""
    reserved = await first_of(run.limits.reserve_task(host), run.context.stop.wait())
    return not reserved.cancelled()


async def _cancel_all(tasks: set[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    # Collect task exceptions so cleanup can finish. TaskFailure's done callbacks handle
    # failures, including a task that raises while being cancelled.
    await asyncio.gather(*tasks, return_exceptions=True)


def _stopping(run: Run) -> bool:
    return run.context.stop.is_set or run.task_failure.is_set


def _closes_the_seed_chain(run: Run) -> bool:
    # The URL limit is a stop that leaves the file whole, so the chain's URLs are still decided
    # against the Scope it ended in; any other stop or a bug ends the run as it is.
    stop = run.context.stop
    return not run.task_failure.is_set and (not stop.is_set or stop.reason == "max_urls")


def _is_checked_url(queued: QueuedUrl, decision: ScopeDecision) -> bool:
    return not decision.in_scope or via_resource(queued)


def _discard(ids: set[int], url_id: int, _: object) -> None:
    ids.discard(url_id)


async def _crawl_url(run: Run, queued: QueuedUrl, decision: ScopeDecision) -> None:
    recorded = await unit_of(run, queued, decision)
    # The task ends at submit; its outcome arrives at commit (020-add-crawl-core D2).
    if recorded is not None:
        await run.outcomes.submit(recorded)
    else:
        # Still queued: one the re-dispatch list owns waits there, since no frontier read
        # dispatches it again.
        run.redispatch.put_back([queued])
