"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

from openlinx.aio import first_of
from openlinx.clock import Clock
from openlinx.crawl.fetch.fetcher import Fetcher, FetchFailure, FetchResult, Request
from openlinx.crawl.fetch.pause_gate import PauseGate
from openlinx.crawl.fetch.politeness import RateGate, RequestLimits
from openlinx.crawl.urls import NormalizedUrl, host_key
from openlinx.store.records import FetchError

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
    starting, or a stop ended a retry that was due, which leaves the URL queued."""


class Stop(Protocol):
    """One kind of the Crawl's stop, as a request reads it."""

    @property
    def is_set(self) -> bool: ...

    async def wait(self) -> None: ...


class Stops(Protocol):
    """The Crawl's stop flag, as the Requester reads it: any stop keeps a new request from
    starting, and only one that ends what is under way cuts a retry (022 design D4)."""

    @property
    def new_requests(self) -> Stop: ...

    @property
    def under_way(self) -> Stop: ...


class _Never:
    """A probe's stop: the network pause cancels its probes itself (design D16)."""

    is_set = False

    async def wait(self) -> None:
        await asyncio.get_running_loop().create_future()


@dataclass(frozen=True, slots=True)
class Attempted:
    """The last attempt's outcome of a URL's request, how many attempts it took, and whether
    the network pause's closed gate ended its retries while one was due."""

    outcome: FetchResult | FetchFailure
    attempt_count: int
    gated: bool = False


@dataclass(frozen=True, slots=True)
class ProbeResult:
    outcome: FetchResult | FetchFailure
    elapsed_seconds: float


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
        stop: Stops,
    ) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._gate = gate
        self._concurrency = concurrency
        self._clock = clock
        self._watchdog_seconds = watchdog_seconds
        self._new_requests = stop.new_requests
        self._under_way = stop.under_way
        self._starts: deque[float] = deque()
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(cap)
        self._retries = retries
        self._pause_gate = PauseGate()

    def close_gate(self) -> None:
        self._pause_gate.close()

    def open_gate(self) -> None:
        self._pause_gate.open()

    async def request_url(
        self, url: NormalizedUrl, on_attempt: Callable[[FetchResult | FetchFailure], None]
    ) -> Attempted | NotStarted:
        """A URL's own request, with its retries. The URL limit counts the first attempt, with
        the slots held, so the count is exact; a retry is the same URL (022 design D4). After a
        stop, none starts (design D16). `on_attempt` hears each attempt's outcome as it ends,
        so the network pause counts a URL before its retries (022 design D4)."""
        async with self._gated_slots(url, self._new_requests) as passed:
            # Refused with its turn under --rate already taken, and never given back: after a
            # stop or at the limit, no request starts again.
            if not passed or not self._limits.start_request():
                return NotStarted()
            self._starts.append(self._clock.monotonic())
            outcome = await self._send(url)
            on_attempt(outcome)
        retried = await self._retried(url, outcome, on_attempt, ends_at_gate=True)
        if isinstance(retried, NotStarted):
            # Given back unrecorded, so a continue requests it (022 design D4).
            self.give_back()
        return retried

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
        counts (design D6). After a stop, none starts (design D16). A retry waits at the network
        pause's gate: robots.txt is no URL of the pause's count, and its origin's URLs wait for
        its verdict (022 design D4)."""
        async with self._gated_slots(url, self._new_requests) as passed:
            if not passed:
                return NotStarted()
            outcome = await self._send(url)
        retried = await self._retried(url, outcome, _unheard, ends_at_gate=False)
        return retried if isinstance(retried, NotStarted) else retried.outcome

    async def request_probe(self, url: NormalizedUrl) -> ProbeResult:
        """A probe of the network pause: through the host's slot, its turn and the global cap,
        but never the pause's gate or the URL limit (design D16)."""
        async with self._slots(url, _Never()) as passed:
            if not passed:
                raise RuntimeError("A probe cannot be refused by its never-set stop")
            started = self._clock.monotonic()
            outcome = await self._send(url)
            return ProbeResult(outcome, self._clock.monotonic() - started)

    async def _retried(
        self,
        url: NormalizedUrl,
        outcome: FetchResult | FetchFailure,
        on_attempt: Callable[[FetchResult | FetchFailure], None],
        *,
        ends_at_gate: bool,
    ) -> Attempted | NotStarted:
        """The URL limit's stop refuses new URLs only, so the retries go on within its grace;
        any other stop ends a due retry, and the URL is not recorded (022 design D4)."""
        attempts = 1
        while True:
            wait, pauses = retry_wait(outcome, attempts, self._clock.now())
            # Politeness toward the host, whether or not the URL has a retry left.
            if pauses:
                self._gate.pause(host_key(url), wait)
            if attempts > self._retries or not is_retried(outcome):
                break
            # Outside the slots: a waiting retry holds none of the host's --concurrency.
            if not await self._before(self._under_way, wait):
                return NotStarted()
            # A closed gate ends a URL's retries: an outage spends none, and the network pause
            # decides on the URL from its last outcome (022 design D4).
            async with self._gated_slots(url, self._under_way, ends_at_gate=ends_at_gate) as passed:
                if self._under_way.is_set:
                    return NotStarted()
                if not passed:
                    return Attempted(outcome, attempts, gated=True)
                outcome = await self._send(url)
                on_attempt(outcome)
            attempts += 1
        return Attempted(outcome, attempts)

    @asynccontextmanager
    async def _gated_slots(
        self, url: NormalizedUrl, cutoff: Stop, *, ends_at_gate: bool = False
    ) -> AsyncIterator[bool]:
        """Whether the request passed the gate and holds its slots before `cutoff`; one that
        `ends_at_gate` does not wait at a closed one."""
        # Waited before any slot, so a paused request leaves the host's slots to the probes; one
        # that took them as the pause began gives them back and its turn goes unused.
        while await self._pause_gate.pass_request(ends_at_gate=ends_at_gate):
            async with self._slots(url, cutoff) as held:
                if not held or self._pause_gate.is_open:
                    yield held
                    return
        yield False

    @asynccontextmanager
    async def _slots(self, url: NormalizedUrl, cutoff: Stop) -> AsyncIterator[bool]:
        """Whether the request may start before `cutoff`; any host slot and global permit
        held are released on exit from the context."""
        # The host's slot and reserved turn precede the global permit, so their initial waits
        # leave room for other hosts. After waiting for the permit, started() may still wait
        # out the remaining --rate interval with the permit held.
        host = host_key(url)
        async with self._host(host):
            if not await self._before(cutoff, self._gate.reserve_turn(host)):
                yield False
                return
            while True:
                async with self._requests:
                    paused = self._gate.pause_left(host)
                    if not paused:
                        await self._gate.started(host)
                        yield not cutoff.is_set
                        return
                # A host pause that began while it waited for the permit is waited out without
                # it, so a Retry-After holds no global permit and a stop ends that wait
                # (022 design D4).
                if not await self._before(cutoff, paused):
                    yield False
                    return

    async def _before(self, cutoff: Stop, wait: float) -> bool:
        """Whether `wait` seconds passed before `cutoff`: a request that has not started does
        not sleep out its turn after a stop (design D16)."""
        if cutoff.is_set:
            return False
        if wait <= 0:
            return True
        turn = await first_of(self._clock.sleep(wait), cutoff.wait())
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


def _unheard(outcome: FetchResult | FetchFailure) -> None:
    """robots.txt's attempts: its verdict is counted, by the engine (design D16)."""


def is_retried(outcome: FetchResult | FetchFailure) -> bool:
    if isinstance(outcome, FetchFailure):
        return outcome.fetch_error in RETRIED_FAILURES
    return 500 <= outcome.status_code <= 599 or outcome.status_code == 429


def retry_wait(
    outcome: FetchResult | FetchFailure, attempt: int, ended: datetime
) -> tuple[float, bool]:
    """The seconds before retry `attempt`, and whether the host pauses for them: a
    Retry-After on a 429 or 503 sets them, capped, and a 429 without one waits 10 seconds;
    any other retry backs off, 1, 2, 4, ... seconds (022 design D4). `ended` is when the
    response ended, from which a Retry-After date counts."""
    if isinstance(outcome, FetchResult) and outcome.status_code in (429, 503):
        after = retry_after(outcome, ended)
        if after is not None:
            return min(after, RETRY_AFTER_CAP), True
        if outcome.status_code == 429:
            return TOO_MANY_REQUESTS_WAIT, True
    return 2.0 ** (attempt - 1), False


def retry_after(response: FetchResult, ended: datetime) -> float | None:
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
    return max(0.0, (date - ended).total_seconds())
