"""The Requester: every request of a Crawl, made politely (020-add-crawl-core D7)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

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


@dataclass(frozen=True, slots=True)
class UrlLimitRefused:
    """The URL limit refused a URL's request, which leaves the URL queued."""


@dataclass(frozen=True, slots=True)
class Attempted:
    """The last attempt's outcome of a URL's request, and how many attempts it took."""

    outcome: FetchResult | FetchFailure
    attempt_count: int


class Requester:
    """The host's slot, its turn under --rate, the global cap and the URL limit for every
    request; the watchdog, the network pause and 022's retries belong here, not in its callers."""

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
    ) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._gate = gate
        self._concurrency = concurrency
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(cap)
        self._clock = clock
        self._retries = retries

    async def request_url(self, url: NormalizedUrl) -> Attempted | UrlLimitRefused:
        """A URL's own request, with its retries. The URL limit counts the first attempt, with
        the slots held, so the count is exact; a retry is the same URL (022 design D4)."""
        async with self._slots(url):
            if not self._limits.start_request():
                # The start the gate gave it stays taken: after a refusal, no request starts.
                return UrlLimitRefused()
            outcome = await self._send(url)
        return await self._retried(url, outcome)

    async def request_robots_txt(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """One hop of an origin's robots.txt, with its retries, which the URL limit never
        counts (design D6)."""
        async with self._slots(url):
            outcome = await self._send(url)
        return (await self._retried(url, outcome)).outcome

    async def _retried(self, url: NormalizedUrl, outcome: FetchResult | FetchFailure) -> Attempted:
        attempts = 1
        while True:
            wait, pauses = retry_wait(outcome, attempts)
            # Politeness toward the host, whether or not the URL has a retry left.
            if pauses:
                self._gate.pause(host_key(url), wait)
            if attempts > self._retries or not is_retried(outcome):
                break
            # Outside the slots: a waiting retry holds none of the host's --concurrency.
            await self._clock.sleep(wait)
            async with self._slots(url):
                outcome = await self._send(url)
            attempts += 1
        return Attempted(outcome, attempts)

    @asynccontextmanager
    async def _slots(self, url: NormalizedUrl) -> AsyncIterator[None]:
        # The host's slot, then its turn under --rate, then the global cap: a request waiting
        # for a busy host, or for its turn, holds no global permit.
        host = host_key(url)
        async with self._host(host):
            await self._gate.wait_turn(host)
            async with self._requests:
                await self._gate.started(host)
                yield

    def _host(self, host: str) -> asyncio.Semaphore:
        semaphore = self._hosts.get(host)
        if semaphore is None:
            semaphore = self._hosts[host] = asyncio.Semaphore(self._concurrency)
        return semaphore

    async def _send(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        return await self._fetcher.fetch(Request(url))


def is_retried(outcome: FetchResult | FetchFailure) -> bool:
    """Whether an attempt that ended this way is tried again, while retries are left."""
    if isinstance(outcome, FetchFailure):
        return outcome.fetch_error in RETRIED_FAILURES
    return outcome.status_code >= 500 or outcome.status_code == 429


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
