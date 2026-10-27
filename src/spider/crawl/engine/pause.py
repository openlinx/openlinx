"""The network pause: Internal requests in a row without an HTTP response (020-add-crawl-core
D16)."""

import asyncio
from typing import Literal

from spider.clock import Clock
from spider.crawl.engine.crawl_warnings import network_paused
from spider.crawl.engine.stop import StopSignal
from spider.crawl.engine.warning_log import WarningLog
from spider.crawl.fetch.fetcher import FetchFailure
from spider.crawl.fetch.requester import Requester
from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchError

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
        stop: StopSignal,
        requester: Requester,
        clock: Clock,
        log: WarningLog,
    ) -> None:
        self._limit = pause_after(concurrency)
        self._network_wait = network_wait
        self._seed = seed
        self._stop = stop
        self._requester = requester
        self._clock = clock
        self._log = log
        self._in_a_row = 0
        # The Seed is requested first, so the first Internal answer is its origin's.
        self._seed_answered = False
        self._probing: asyncio.Task[None] | None = None

    def responded(self) -> None:
        self._in_a_row = 0
        self._seed_answered = True

    def robots_txt_answered(self) -> None:
        self._seed_answered = True

    def failed(self, fetch_error: FetchError) -> None:
        if fetch_error not in NO_RESPONSE:
            return
        self._in_a_row += 1
        # Until the Seed's origin answers, one failure pauses: a network may be coming up or
        # switching just as the Crawl starts (design D16).
        if not self._seed_answered:
            self._pause("seed_unreachable")
        elif self._in_a_row >= self._limit:
            self._pause("site_unreachable")

    async def close(self) -> None:
        if self._probing is not None:
            self._probing.cancel()
            await asyncio.gather(self._probing, return_exceptions=True)

    def _pause(self, reason: Literal["seed_unreachable", "site_unreachable"]) -> None:
        if self._network_wait == 0:
            self._stop.set(reason)
        elif self._probing is None:
            self._requester.close_gate()
            self._probing = asyncio.create_task(self._probe(reason))

    async def _probe(self, reason: Literal["seed_unreachable", "site_unreachable"]) -> None:
        began = self._clock.monotonic()
        answered = await self._answered(began)
        self._log.count_pause(network_paused(self._seed), self._clock.monotonic() - began)
        if not answered:
            self._stop.set(reason)
        self._in_a_row = 0
        self._probing = None
        # Open after giving up too: the stop then refuses the requests that waited.
        self._requester.open_gate()

    async def _answered(self, began: float) -> bool:
        """Whether a probe answered before the wait ended, when the probes still in flight are
        cancelled; one that started exactly at the wait is awaited."""
        probes: set[asyncio.Task[bool]] = set()
        at_the_wait: asyncio.Task[bool] | None = None
        try:
            for at in probe_times(self._network_wait):
                if await self._answer_before(probes, began + at):
                    return True
                probe = asyncio.create_task(self._probe_once())
                probes.add(probe)
                if at == self._network_wait:
                    at_the_wait = probe
            if await self._answer_before(probes, began + self._network_wait):
                return True
            return at_the_wait is not None and await at_the_wait
        finally:
            for probe in probes:
                probe.cancel()
            await asyncio.gather(*probes, return_exceptions=True)

    async def _answer_before(self, probes: set[asyncio.Task[bool]], until: float) -> bool:
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
