"""Politeness: how many requests may be in flight, to one host and in all, and how often
they may start (020 D7)."""

import asyncio
import math

from spider.clock import Clock


def is_rate(rate: float) -> bool:
    """The one rule of --rate and crawl.rate: a finite number of requests per second above 0."""
    return math.isfinite(rate) and rate > 0


class RateGate:
    """--rate: requests to one host start at least 1/rate seconds apart, on the clock."""

    def __init__(self, clock: Clock, rate: float | None) -> None:
        self._clock = clock
        self._interval = None if rate is None else 1 / rate
        self._turns: dict[str, asyncio.Lock] = {}
        self._next_starts: dict[str, float] = {}

    async def wait_turn(self, host: str) -> None:
        if self._interval is None:
            return
        turn = self._turns.get(host)
        if turn is None:
            turn = self._turns[host] = asyncio.Lock()
        # One waiter per host at a time, so the starts follow one another in order.
        async with turn:
            now = self._clock.monotonic()
            start = max(now, self._next_starts.get(host, now))
            if start > now:
                await self._clock.sleep(start - now)
            self._next_starts[host] = start + self._interval


def global_cap(concurrency: int) -> int:
    """Bounds sockets when many External hosts are checked at once."""
    return min(100, max(20, 4 * concurrency))


class RequestLimits:
    """A semaphore per host, the global cap on requests in flight, the bound on URL tasks, and
    the URL limit, --max-urls, which counts every request it lets start.

    A task holds its permit until its unit is submitted, so `backlog` is how far page
    preparation may fall behind the requests before fetching waits (design D7, 026 D2).
    """

    def __init__(self, concurrency: int, backlog: int = 0, max_urls: int | None = None) -> None:
        self._concurrency = concurrency
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(global_cap(concurrency))
        self._tasks = asyncio.Semaphore(global_cap(concurrency) + backlog)
        self._max_urls = max_urls
        self._started = 0
        self._refused: int | None = None

    def start_request(self) -> bool:
        """Counts a URL request as it starts, in flight from then on, or refuses it at the URL
        limit; called with its host's slot and the global cap held, so the count is exact."""
        if self.refuses():
            self.refuse()
            return False
        self._started += 1
        return True

    def refuses(self) -> bool:
        """Whether the URL limit would refuse a new request now."""
        return self._max_urls is not None and self._started >= self._max_urls

    def refuse(self) -> None:
        """Marks the limit reached: a refused request leaves its URL queued."""
        self._refused = self._max_urls

    def limit_reached(self) -> int | None:
        """The URL limit once it has refused a request."""
        return self._refused

    async def reserve_task(self) -> None:
        """Waits for room under the global cap before a URL's task is created."""
        await self._tasks.acquire()

    def task_ended(self) -> None:
        self._tasks.release()

    def request(self) -> asyncio.Semaphore:
        """Taken after the host's slot, so a URL waiting for a busy host holds no permit."""
        return self._requests

    def host(self, host: str) -> asyncio.Semaphore:
        semaphore = self._hosts.get(host)
        if semaphore is None:
            semaphore = self._hosts[host] = asyncio.Semaphore(self._concurrency)
        return semaphore
