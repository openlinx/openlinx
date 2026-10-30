"""The network pause: Internal requests in a row without an HTTP response (020-add-crawl-core
D16)."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from openlinx.aio import first_of
from openlinx.clock import Clock
from openlinx.crawl.engine.crawl_warnings import network_paused
from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.engine.warning_log import WarningLog
from openlinx.crawl.fetch.fetcher import FetchFailure, FetchResult
from openlinx.crawl.fetch.requester import Attempted, Requester
from openlinx.crawl.scope import ScopeDecision
from openlinx.crawl.urls import NormalizedUrl, url_origin
from openlinx.store.records import FetchError, QueuedUrl

# tls_error is not among them: a certificate failure is an answer of sorts, and a site-wide one
# must not wait --network-wait and then fail as site_unreachable.
_NO_RESPONSE: frozenset[FetchError] = frozenset(
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
    """When the probes of a pause start, each before the wait ends: one at the wait would hold
    the Crawl past it (design D16)."""
    times = [t for t in _FIRST_PROBES if t < network_wait]
    later = _FIRST_PROBES[-1] + _PROBE_INTERVAL
    times += range(later, network_wait, _PROBE_INTERVAL)
    return tuple(times)


type _Reason = Literal["seed_unreachable", "site_unreachable"]
type PauseEnd = Literal["dead_section", "outage"]


@dataclass(frozen=True, slots=True)
class CountedUrl:
    """A URL of the count, and whether its own request counted toward the URL limit: one
    recorded from its origin's failed robots.txt was never requested."""

    queued: QueuedUrl
    requested: bool


@dataclass(frozen=True, slots=True)
class _Paused:
    """A pause: why it began, and when."""

    reason: _Reason
    began: float


class Redispatch:
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

    def requeue(self, count: Sequence[CountedUrl]) -> list[CountedUrl]:
        """The count's URLs to put back in the queue: those not re-queued before."""
        requeued = []
        for counted in count:
            if counted.queued.id not in self._requeued:
                self._requeued.add(counted.queued.id)
                self.add(counted.queued)
                requeued.append(counted)
        return requeued

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

    def put_back(self, urls: Sequence[QueuedUrl]) -> None:
        """URLs this list took that are still queued: not started, or ended without a record,
        such as one refused at the URL limit. Only this list may dispatch them, so they wait
        here for its next take (design D16)."""
        for queued in urls:
            if queued.id in self._owned:
                self._urls[queued.id] = queued


class NetworkPause:
    """Kept from each URL's outcome, which the engine hands it with the URL's dispatch decision,
    since only the engine knows which URLs are Internal, and every code that counts, a
    robots.txt one included; it decides whether a URL is recorded or re-queued, and the
    Requester holds its gate and makes its probes (design D7, D16)."""

    def __init__(
        self,
        *,
        concurrency: int,
        network_wait: int,
        seed: NormalizedUrl,
        crawl_id: str,
        seed_answered: bool,
        stop: StopSignal,
        requester: Requester,
        redispatch: Redispatch,
        clock: Clock,
        warnings: WarningLog,
        resumed: Callable[[PauseEnd, Sequence[CountedUrl]], Awaitable[None]],
        track: Callable[[asyncio.Task[None]], None],
    ) -> None:
        """`track` hands the probing task to the run's TaskFailure, which ends the run on its
        error; `seed_answered` is whether the Seed's origin answered in an earlier run."""
        self._limit = pause_after(concurrency)
        self._network_wait = network_wait
        self._seed = seed
        self._crawl_id = crawl_id
        self._stop = stop
        self._requester = requester
        self._redispatch = redispatch
        self._clock = clock
        self._warnings = warnings
        self._resumed = resumed
        self._track = track
        # The URLs of the requests in a row without a response, which make up the next count.
        self._in_a_row: list[CountedUrl] = []
        self._paused: _Paused | None = None
        # The pause's own count, which a response while paused never clears, since only the
        # next count starts again (design D16).
        self._count: list[CountedUrl] = []
        # The Seed is requested first, so the first Internal answer is its origin's; a
        # continue that does not request it again takes the earlier runs' answer.
        self._seed_answered = seed_answered
        # The origins that a dead section showed dead, which count no more (design D16).
        self._dead_origins: set[str] = set()
        # The URLs of the count whose request was recorded as an error: an outage re-queues only
        # them, never one still in its retries, fetched, or back in the queue unrecorded.
        self._recorded: set[int] = set()
        self._probing: asyncio.Task[None] | None = None

    @property
    def paused(self) -> bool:
        return self._probing is not None

    @property
    def counting(self) -> bool:
        """Whether the count is open: paused, or Internal requests failing in a row, whose URLs
        a pause may give back."""
        return self.paused or bool(self._in_a_row)

    def _responded(self) -> None:
        self._in_a_row.clear()
        if self._paused is None:
            self._recorded.clear()
        self._seed_answered = True

    def attempts_of(
        self, queued: QueuedUrl, *, internal: bool
    ) -> Callable[[FetchResult | FetchFailure], None]:
        """What the attempts of a URL's request tell the pause: an Internal URL counts once, at
        its first attempt without a response, and a response resets the count, so the count
        follows dispatch order and a dead network pauses the Crawl before the retries
        (022-add-fetch-policy D4). One that fails while paused counts not: it is re-queued."""
        counted = False

        def attempted(outcome: FetchResult | FetchFailure) -> None:
            nonlocal counted
            if not internal:
                return
            if not isinstance(outcome, FetchFailure):
                self._responded()
            elif not counted and not self.paused and outcome.fetch_error in _NO_RESPONSE:
                counted = True
                self._failed(outcome.fetch_error, queued, requested=True)

        return attempted

    def outcome(self, queued: QueuedUrl, decision: ScopeDecision, attempted: Attempted) -> bool:
        """Whether a URL's request is recorded. One that ended without a response while paused
        is not, nor one whose due retry the closed gate ended, whatever its last answer, so its
        URL stays queued, is dispatched again, and counts toward the URL limit only then (design
        D16). A URL of the count that failed is recorded, so the pause's end decides on it: an
        outage re-queues it, once a run, and a dead section keeps its error
        (022-add-fetch-policy D4)."""
        response = attempted.outcome
        if not isinstance(response, FetchFailure):
            if attempted.gated:
                self._requeue(queued)
                return False
            return True
        if _holds(self._count, queued):
            self._recorded.add(queued.id)
            return True
        if attempted.gated or (self.paused and response.fetch_error in _NO_RESPONSE):
            self._requeue(queued)
            return False
        if decision.is_internal and _holds(self._in_a_row, queued):
            self._recorded.add(queued.id)
        return True

    def _requeue(self, queued: QueuedUrl) -> None:
        self._requester.give_back()
        self._redispatch.add(queued)

    def verdict(
        self, queued: QueuedUrl, decision: ScopeDecision, origin_error: FetchError | None
    ) -> None:
        """What the robots.txt verdict of an Internal URL's origin tells the pause: one without
        a response counts, for the URL it records without a request of its own (design D6)."""
        if not decision.is_internal:
            return
        if origin_error is None:
            self._seed_answered = True
        else:
            self._failed(origin_error, queued, requested=False)

    def _failed(self, fetch_error: FetchError, queued: QueuedUrl, *, requested: bool) -> None:
        if fetch_error not in _NO_RESPONSE or url_origin(queued.url) in self._dead_origins:
            return
        counted = CountedUrl(queued, requested)
        if self._paused is not None:
            self._count.append(counted)
            return
        self._in_a_row.append(counted)
        # Until the Seed's origin answers, one failure pauses: a network may be coming up or
        # switching just as the Crawl starts (design D16).
        if not self._seed_answered:
            self._pause("seed_unreachable", fetch_error)
        elif len(self._in_a_row) >= self._limit:
            self._pause("site_unreachable", fetch_error)

    async def ended(self) -> None:
        # Its error, if any, is the TaskFailure's.
        if self._probing is not None:
            await asyncio.wait({self._probing})

    async def close(self) -> None:
        if self._probing is not None:
            self._probing.cancel()
            await asyncio.gather(self._probing, return_exceptions=True)

    def _pause(self, reason: _Reason, fetch_error: FetchError) -> None:
        if self._network_wait == 0:
            self._stop.set(reason)
        elif self._probing is None:
            paused = _Paused(reason, self._clock.monotonic())
            self._count = list(self._in_a_row)
            self._paused = paused
            self._in_a_row.clear()
            self._requester.close_gate()
            self._warnings.event(
                "crawl_paused",
                crawl_id=self._crawl_id,
                reason=fetch_error,
                urls=[counted.queued.url for counted in self._count],
            )
            # As the pause begins, so a reader of stderr learns of it then.
            self._warnings.pause_began(network_paused(self._seed))
            self._probing = asyncio.create_task(self._probe(paused))
            self._track(self._probing)

    async def _probe(self, paused: _Paused) -> None:
        try:
            end = await self._wait_for_answer(paused.began)
            if end == "dead_section" and paused.reason == "seed_unreachable":
                # The Seed is no section of the site: its first answer is the network's, so its
                # robots.txt and the Seed are requested again (design D16).
                end = "outage"
            if end == "dead_section":
                self._count_no_more(self._count)
            seconds = self._clock.monotonic() - paused.began
            if end is None:
                # A stop that ended the wait keeps its reason; giving up sets the pause's.
                if not self._stop.ends_under_way:
                    self._stop.set(paused.reason)
            else:
                count = (
                    counted
                    for counted in self._count
                    if not counted.requested or counted.queued.id in self._recorded
                )
                await self._resumed(end, tuple(count))
                self._warnings.event(
                    "crawl_resumed",
                    crawl_id=self._crawl_id,
                    duration_s=round(seconds, 3),
                    outcome=end,
                )
        finally:
            # However the pause ends, a stop or the run's end included, its seconds count.
            self._warnings.pause_ended(self._clock.monotonic() - paused.began)
            self._paused = None
            self._count = []
            self._recorded.clear()
            self._probing = None
            # Open after giving up or failing too: the stop or the run's end then refuses the
            # requests that waited, where a closed gate would hold them for good.
            self._requester.open_gate()

    def _count_no_more(self, count: Sequence[CountedUrl]) -> None:
        """The origins with at least 2 URLs in the count: one transient failure of a working
        origin inside a dead one's streak shows nothing. The probes request the Seed, so its
        answer never shows the Seed's origin dead, and an outage of a site on one host must
        still pause (design D16)."""
        failures = Counter(url_origin(counted.queued.url) for counted in count)
        dead = {origin for origin, n in failures.items() if n >= 2}
        self._dead_origins.update(dead - {url_origin(self._seed)})

    async def _wait_for_answer(self, began: float) -> PauseEnd | None:
        """How the pause ended: a probe answered before the wait ended, or none did, or the
        Crawl stopped, and every probe still in flight is cancelled then. The first probe's
        answer means a dead section, a later one's an outage."""
        probes: list[asyncio.Task[bool]] = []
        times = probe_times(self._network_wait)
        # A first probe that hangs in its connection may answer only after the network came
        # back, so its answer means a dead section only before the second probe is due.
        dead_before = began + (times[1] if len(times) > 1 else self._network_wait)
        try:
            for at in times:
                if await self._answer_before(probes, began + at):
                    return self._end(probes, dead_before)
                if self._stop.ends_under_way:
                    return None
                probes.append(asyncio.create_task(self._probe_once()))
            if await self._answer_before(probes, began + self._network_wait):
                return self._end(probes, dead_before)
            return None
        finally:
            for probe in probes:
                probe.cancel()
            await asyncio.gather(*probes, return_exceptions=True)

    async def _answer_before(self, probes: list[asyncio.Task[bool]], until: float) -> bool:
        """Whether a probe answered by `until`; a stop ends the wait with no answer (design
        D16), but for the URL limit's, which refuses new URLs only (022-add-fetch-policy D4)."""
        while not any(_answered(probe) for probe in probes):
            delay = until - self._clock.monotonic()
            if delay <= 0 or self._stop.ends_under_way:
                return False
            waiting = {probe for probe in probes if not probe.done()}
            await first_of(
                self._clock.sleep(delay), self._stop.wait_ending_under_way(), wake_on=waiting
            )
        return True

    def _end(self, probes: list[asyncio.Task[bool]], dead_before: float) -> PauseEnd:
        if _answered(probes[0]) and self._clock.monotonic() < dead_before:
            return "dead_section"
        return "outage"

    async def _probe_once(self) -> bool:
        response = await self._requester.request_probe(self._seed)
        return not isinstance(response, FetchFailure)


def _answered(probe: asyncio.Task[bool]) -> bool:
    return probe.done() and not probe.cancelled() and probe.result()


def _holds(count: Sequence[CountedUrl], queued: QueuedUrl) -> bool:
    return any(counted.queued.id == queued.id for counted in count)
