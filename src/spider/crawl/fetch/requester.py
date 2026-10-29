"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Protocol

from spider.aio import first_of
from spider.clock import Clock
from spider.crawl.fetch.fetcher import Fetcher, FetchFailure, FetchResult, Request
from spider.crawl.fetch.politeness import RateGate, RequestLimits
from spider.crawl.urls import NormalizedUrl, host_key
from spider.store.records import FetchError

# The failures that may pass on a later attempt (022 design D4). A DNS, TLS or protocol error
# is the name's or the server's answer, and the watchdog has waited past --timeout already.
RETRIED_FAILURES: frozenset[FetchError] = frozenset(
    {"timeout", "connection_refused", "connection_error"}
)
# A Retry-After past this is a server asking for more than one URL's retry should wait.
RETRY_AFTER_CAP = 120.0
TOO_MANY_REQUESTS_WAIT = 10.0


def watchdog_seconds(request_deadline_seconds: float) -> float:
    """How long a request attempt may take before the watchdog ends it: a backstop behind the
    Fetcher's own deadline, which it never cuts (design D16)."""
    return max(120, request_deadline_seconds + 30)


# The rate of progress events counts the URL requests started this long ago or since.
RATE_WINDOW_SECONDS = 60


@dataclass(frozen=True, slots=True)
class NotStarted:
    """A stop or the URL limit kept a URL's request, or its origin's robots.txt request, from
    starting, which leaves the URL queued."""


class Stop(Protocol):
    """The Crawl's stop flag, as the Requester reads it."""

    @property
    def is_set(self) -> bool: ...

    async def wait(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Attempted:
    """The last attempt's outcome of a URL's request, and how many attempts it took."""

    outcome: FetchResult | FetchFailure
    attempt_count: int


class Requester:
    """The host's slot, its turn under --rate, the global cap, the URL limit and the watchdog
    for every request, a URL's retries (022 design D4), and the network pause's gate and
    probes; the engine decides from a URL's outcome whether the pause retries it (design D7,
    D16)."""

    def __init__(
        self,
        fetcher: Fetcher,
        limits: RequestLimits,
        gate: RateGate,
        *,
        concurrency: int,
        cap: int,
        clock: Clock,
        retries: int,
        watchdog_seconds: float,
        stop: Stop,
    ) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._gate = gate
        self._concurrency = concurrency
        self._clock = clock
        self._watchdog_seconds = watchdog_seconds
        self._stop = stop
        self._starts: deque[float] = deque()
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(cap)
        self._retries = retries
        # The network pause's gate: set while requests may start (design D16).
        self._open = asyncio.Event()
        self._open.set()
        # The requests still waiting at the gate, and the event of their last one.
        self._at_gate = 0
        self._gate_drained = asyncio.Event()

    def close_gate(self) -> None:
        self._open.clear()

    def open_gate(self) -> None:
        self._open.set()

    async def request_url(self, url: NormalizedUrl) -> Attempted | NotStarted:
        """A URL's own request, with its retries. The URL limit counts the first attempt, with
        the slots held, so the count is exact; a retry is the same URL (022 design D4). After a
        stop, none starts (design D16)."""
        async with self._gated_slots(url):
            # Refused with its turn under --rate already taken, and never given back: after a
            # stop or at the limit, no request starts again.
            if self._stop.is_set or not self._limits.start_request():
                return NotStarted()
            self._starts.append(self._clock.monotonic())
            outcome = await self._send(url)
        return await self._retried(url, outcome)

    def give_back(self) -> None:
        """A URL request that is made again, as if it had not started (design D16)."""
        self._limits.give_back()
        if self._starts:
            self._starts.pop()

    def rate(self, elapsed: float) -> float:
        """URL requests started per second, over the window or the `elapsed` seconds the run
        has lasted when that is shorter."""
        oldest = self._clock.monotonic() - RATE_WINDOW_SECONDS
        while self._starts and self._starts[0] <= oldest:
            self._starts.popleft()
        seconds = min(RATE_WINDOW_SECONDS, elapsed)
        return round(len(self._starts) / seconds, 3) if seconds > 0 else 0.0

    async def request_robots_txt(
        self, url: NormalizedUrl
    ) -> FetchResult | FetchFailure | NotStarted:
        """One hop of an origin's robots.txt, with its retries, which the URL limit never
        counts (design D6). After a stop, none starts (design D16)."""
        async with self._gated_slots(url):
            if self._stop.is_set:
                return NotStarted()
            outcome = await self._send(url)
        return (await self._retried(url, outcome)).outcome

    async def request_probe(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """A probe of the network pause: through the host's slot, its turn and the global cap,
        but never the pause's gate or the URL limit (design D16)."""
        async with self._slots(url, stops=False):
            return await self._send(url)

    async def _retried(self, url: NormalizedUrl, outcome: FetchResult | FetchFailure) -> Attempted:
        attempts = 1
        while True:
            wait, pauses = retry_wait(outcome, attempts)
            # Politeness toward the host, whether or not the URL has a retry left.
            if pauses:
                self._gate.pause(host_key(url), wait)
            if attempts > self._retries or not is_retried(outcome):
                break
            # Outside the slots: a waiting retry holds none of the host's --concurrency. After a
            # stop, the last attempt's outcome is the URL's.
            if not await self._turn_before_stop(wait):
                break
            async with self._gated_slots(url):
                if self._stop.is_set:
                    break
                outcome = await self._send(url)
            attempts += 1
        return Attempted(outcome, attempts)

    @asynccontextmanager
    async def _gated_slots(self, url: NormalizedUrl) -> AsyncIterator[None]:
        # Waited before any slot, so a paused request leaves the host's slots to the probes; one
        # that took them as the pause began gives them back and its turn goes unused.
        while True:
            await self._past_gate()
            async with self._slots(url, stops=True):
                if self._open.is_set():
                    yield
                    return

    async def _past_gate(self) -> None:
        """Those that waited at the gate wake a loop turn or more after it opens: a request
        that comes since then goes behind them, so requests reach the host's slot in the order
        they were dispatched (design D1)."""
        while self._at_gate:
            await self._gate_drained.wait()
        if self._open.is_set():
            return
        if not self._at_gate:
            self._gate_drained = asyncio.Event()
        self._at_gate += 1
        try:
            await self._open.wait()
        finally:
            self._at_gate -= 1
            if not self._at_gate:
                self._gate_drained.set()

    @asynccontextmanager
    async def _slots(self, url: NormalizedUrl, *, stops: bool) -> AsyncIterator[None]:
        # The host's slot, then its turn under --rate, then the global cap: a request waiting
        # for a busy host, or for its turn, holds no global permit.
        host = host_key(url)
        async with self._host(host):
            wait = self._gate.reserve_turn(host)
            if stops:
                if not await self._turn_before_stop(wait):
                    # Its caller sees the stop and starts nothing.
                    yield
                    return
            elif wait > 0:
                await self._clock.sleep(wait)
            async with self._requests:
                await self._gate.started(host)
                yield

    async def _turn_before_stop(self, wait: float) -> bool:
        """Whether the turn came before the stop flag: a request that has not started does not
        sleep out its turn after a stop (design D16)."""
        if self._stop.is_set:
            return False
        if wait <= 0:
            return True
        turn = await first_of(self._clock.sleep(wait), self._stop.wait())
        return not turn.cancelled()

    def _host(self, host: str) -> asyncio.Semaphore:
        semaphore = self._hosts.get(host)
        if semaphore is None:
            semaphore = self._hosts[host] = asyncio.Semaphore(self._concurrency)
        return semaphore

    async def _send(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        # Each attempt races its own watchdog on the Crawl's Clock, from when it started, which
        # its row keeps as the Fetcher's would.
        started_at = self._clock.now()
        # Both have ended before the slots are given back.
        fetch = await first_of(
            self._fetcher.fetch(Request(url)), self._clock.sleep(self._watchdog_seconds)
        )
        if not fetch.cancelled():
            return fetch.result()
        return FetchFailure(
            fetch_error="watchdog",
            message=f"No response within {self._watchdog_seconds:g} seconds",
            fetched_at=started_at,
        )


def is_retried(outcome: FetchResult | FetchFailure) -> bool:
    """Whether an attempt that ended this way is tried again, while retries are left."""
    if isinstance(outcome, FetchFailure):
        return outcome.fetch_error in RETRIED_FAILURES
    return 500 <= outcome.status_code <= 599 or outcome.status_code == 429


def retry_wait(outcome: FetchResult | FetchFailure, attempt: int) -> tuple[float, bool]:
    """The seconds before retry `attempt`, and whether the host pauses for them: a
    Retry-After on a 429 or 503 sets them, capped, and a 429 without one waits 10 seconds;
    any other retry backs off, 1, 2, 4, ... seconds (022 design D4)."""
    if isinstance(outcome, FetchResult) and outcome.status_code in (429, 503):
        after = retry_after(outcome)
        if after is not None:
            return min(after, RETRY_AFTER_CAP), True
        if outcome.status_code == 429:
            return TOO_MANY_REQUESTS_WAIT, True
    return 2.0 ** (attempt - 1), False


def retry_after(response: FetchResult) -> float | None:
    """The response's Retry-After in seconds, from a number of seconds or an HTTP date; None
    without a header that reads as either."""
    value = response.header("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if date.tzinfo is None:
        return None
    return max(0.0, (date - response.fetched_at).total_seconds())
