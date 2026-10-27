"""The network pause: Internal requests in a row without an HTTP response (020-add-crawl-core
D16)."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from spider.clock import Clock
from spider.crawl.engine.crawl_warnings import network_paused
from spider.crawl.engine.stop import StopSignal
from spider.crawl.engine.warning_log import WarningLog
from spider.crawl.fetch.fetcher import FetchFailure
from spider.crawl.fetch.requester import Requester
from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchError, QueuedUrl

# tls_error is not among them: a certificate failure is an answer of sorts, and a site-wide one
# must not wait --network-wait and then fail as site_unreachable.
NO_RESPONSE: frozenset[FetchError] = frozenset(
    {
        "dns_error",
        "connection_refused",
        "connection_error",
        "invalid_response",
        "watchdog",
        "timeout",
    }
)


def pause_after(concurrency: int) -> int:
    return max(8, 2 * concurrency)


# Seconds after the pause began.
_FIRST_PROBES = (5, 10, 20, 40)
_PROBE_INTERVAL = 60


def probe_times(network_wait: int) -> tuple[int, ...]:
    """When the probes of a pause start; one exactly at the wait still starts (design D16)."""
    times = [t for t in _FIRST_PROBES if t <= network_wait]
    later = _FIRST_PROBES[-1] + _PROBE_INTERVAL
    times += range(later, network_wait + 1, _PROBE_INTERVAL)
    return tuple(times)


type _Reason = Literal["seed_unreachable", "site_unreachable"]
type Outcome = Literal["dead_section", "outage"]


class Again:
    """The URLs to dispatch ahead of the frontier read, since its cursor has passed them: those
    an outage re-queues, each at most once a run, and those a pause left queued (design D3,
    D16)."""

    def __init__(self) -> None:
        self._urls: dict[int, QueuedUrl] = {}
        self._requeued: set[int] = set()
        # The URLs this list has dispatched, which it alone dispatches from then on: below the
        # cursor, a frontier read may meet one that has already ended, or is in flight.
        self._owned: set[int] = set()

    def add(self, queued: QueuedUrl) -> None:
        self._urls[queued.id] = queued

    def requeue(self, count: Sequence[QueuedUrl]) -> list[int]:
        """The ids of the count's URLs to put back in the queue: those not re-queued before."""
        ids = []
        for queued in count:
            if queued.id not in self._requeued:
                self._requeued.add(queued.id)
                self.add(queued)
                ids.append(queued.id)
        return ids

    def claim(self, url_id: int) -> bool:
        """Whether the frontier, which read the URL itself, may dispatch it: not one this list
        has dispatched; one still waiting here leaves it, so it is not dispatched twice."""
        if url_id in self._owned:
            return False
        self._urls.pop(url_id, None)
        return True

    def take(self) -> list[QueuedUrl]:
        urls, self._urls = list(self._urls.values()), {}
        self._owned.update(queued.id for queued in urls)
        return urls


class NetworkPause:
    """Kept by the engine from each Internal URL's outcome, since only it knows which URLs are
    Internal and every code that counts, a robots.txt one included; the Requester holds its
    gate and makes its probes (design D7, D16)."""

    def __init__(
        self,
        *,
        concurrency: int,
        network_wait: int,
        seed: NormalizedUrl,
        crawl_id: str,
        stop: StopSignal,
        requester: Requester,
        clock: Clock,
        log: WarningLog,
        resumed: Callable[[Outcome, Sequence[QueuedUrl]], Awaitable[None]],
    ) -> None:
        self._limit = pause_after(concurrency)
        self._network_wait = network_wait
        self._seed = seed
        self._crawl_id = crawl_id
        self._stop = stop
        self._requester = requester
        self._clock = clock
        self._log = log
        self._resumed = resumed
        # The URLs of the requests in a row without a response, which make up the count.
        self._in_a_row: list[QueuedUrl] = []
        # The Seed is requested first, so the first Internal answer is its origin's.
        self._seed_answered = False
        self._probing: asyncio.Task[None] | None = None

    @property
    def paused(self) -> bool:
        return self._probing is not None

    def responded(self) -> None:
        self._in_a_row.clear()
        self._seed_answered = True

    def robots_txt_answered(self) -> None:
        self._seed_answered = True

    def failed(self, fetch_error: FetchError, queued: QueuedUrl) -> None:
        if fetch_error not in NO_RESPONSE:
            return
        self._in_a_row.append(queued)
        # Until the Seed's origin answers, one failure pauses: a network may be coming up or
        # switching just as the Crawl starts (design D16).
        if not self._seed_answered:
            self._pause("seed_unreachable", fetch_error)
        elif len(self._in_a_row) >= self._limit:
            self._pause("site_unreachable", fetch_error)

    async def ended(self) -> None:
        if self._probing is not None:
            await asyncio.shield(self._probing)

    async def close(self) -> None:
        if self._probing is not None:
            self._probing.cancel()
            await asyncio.gather(self._probing, return_exceptions=True)

    def _pause(self, reason: _Reason, fetch_error: FetchError) -> None:
        if self._network_wait == 0:
            self._stop.set(reason)
        elif self._probing is None:
            self._requester.close_gate()
            self._log.event(
                "crawl_paused",
                crawl_id=self._crawl_id,
                reason=fetch_error,
                urls=[queued.url for queued in self._in_a_row],
            )
            self._probing = asyncio.create_task(self._probe(reason))

    async def _probe(self, reason: _Reason) -> None:
        began = self._clock.monotonic()
        outcome = await self._answered(began)
        if outcome == "dead_section" and reason == "seed_unreachable":
            # The Seed is no section of the site: its first answer is the network's, so its
            # robots.txt and the Seed are requested again (design D16).
            outcome = "outage"
        seconds = self._clock.monotonic() - began
        self._log.count_pause(network_paused(self._seed), seconds)
        if outcome is None:
            self._stop.set(reason)
        else:
            await self._resumed(outcome, tuple(self._in_a_row))
            self._log.event(
                "crawl_resumed",
                crawl_id=self._crawl_id,
                duration_s=round(seconds, 3),
                outcome=outcome,
            )
        self._in_a_row.clear()
        self._probing = None
        # Open after giving up too: the stop then refuses the requests that waited.
        self._requester.open_gate()

    async def _answered(self, began: float) -> Outcome | None:
        """How a probe answered before the wait ended, when the probes still in flight are
        cancelled; one that started exactly at the wait is awaited. The first probe's answer
        means a dead section, a later one's an outage."""
        probes: list[asyncio.Task[bool]] = []
        at_the_wait: asyncio.Task[bool] | None = None
        try:
            for at in probe_times(self._network_wait):
                if await self._answer_before(probes, began + at):
                    return _outcome(probes)
                probe = asyncio.create_task(self._probe_once())
                probes.append(probe)
                if at == self._network_wait:
                    at_the_wait = probe
            if await self._answer_before(probes, began + self._network_wait) or (
                at_the_wait is not None and await at_the_wait
            ):
                return _outcome(probes)
            return None
        finally:
            for probe in probes:
                probe.cancel()
            await asyncio.gather(*probes, return_exceptions=True)

    async def _answer_before(self, probes: list[asyncio.Task[bool]], until: float) -> bool:
        while not any(_answered(probe) for probe in probes):
            delay = until - self._clock.monotonic()
            if delay <= 0:
                return False
            sleep = asyncio.ensure_future(self._clock.sleep(delay))
            waiting = {probe for probe in probes if not probe.done()}
            try:
                await asyncio.wait({sleep, *waiting}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                sleep.cancel()
                await asyncio.wait({sleep})
        return True

    async def _probe_once(self) -> bool:
        response = await self._requester.request_probe(self._seed)
        return not isinstance(response, FetchFailure)


def _answered(probe: asyncio.Task[bool]) -> bool:
    return probe.done() and not probe.cancelled() and probe.result()


def _outcome(probes: list[asyncio.Task[bool]]) -> Outcome:
    return "dead_section" if _answered(probes[0]) else "outage"
