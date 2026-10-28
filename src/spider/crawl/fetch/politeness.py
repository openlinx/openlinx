"""Politeness: request limits, the URL limit, --rate, runs of 403s (020-add-crawl-core D7)."""

import asyncio

from spider.clock import Clock


class RateGate:
    """--rate: requests to one host start at least 1/rate seconds apart, on the clock."""

    def __init__(self, clock: Clock, rate: float | None) -> None:
        self._clock = clock
        self._interval = None if rate is None else 1 / rate
        self._next_starts: dict[str, float] = {}
        self._last_starts: dict[str, float] = {}

    def reserve_turn(self, host: str) -> float:
        """The seconds until the host's next turn, which is the caller's from now on."""
        if self._interval is None:
            return 0.0
        now = self._clock.monotonic()
        start = max(now, self._next_starts.get(host, now))
        # Reserved before the wait, so the host's waiters take turns in order, and hold no
        # lock that would make one host's wait another's.
        self._next_starts[host] = start + self._interval
        return start - now

    async def started(self, host: str) -> None:
        """With the global permit held: waits out what is left of the interval since the
        host's last start, which only a wait for the permit leaves."""
        if self._interval is None:
            return
        now = self._clock.monotonic()
        last = self._last_starts.get(host)
        start = now if last is None else max(now, last + self._interval)
        # Taken before the wait, so the next caller counts from this start.
        self._last_starts[host] = start
        if start > now:
            await self._clock.sleep(start - now)


# Consecutive 403 and 429 responses of one host before the warning that it may be blocking.
BLOCKING_RUN = 10
_BLOCKING_STATUSES = frozenset({403, 429})


class BlockingRuns:
    """The run of consecutive 403 and 429 responses of each Internal host, in the order
    they complete."""

    def __init__(self) -> None:
        self._runs: dict[str, int] = {}

    def responded(self, host: str, status_code: int | None) -> bool:
        """Whether the host's run has just reached BLOCKING_RUN; a request without an HTTP
        response, None, leaves the run as it is."""
        if status_code is None:
            return False
        run = self._runs.get(host, 0) + 1 if status_code in _BLOCKING_STATUSES else 0
        self._runs[host] = run
        return run == BLOCKING_RUN


def global_cap(concurrency: int) -> int:
    """Bounds sockets when many External hosts are checked at once."""
    return min(100, max(20, 4 * concurrency))


class RequestLimits:
    """The bound on URL tasks and the URL limit, --max-urls, which counts every request it
    lets start; the Requester holds the hosts' slots and the global cap.

    A task holds its permit until its unit is submitted, so `backlog` is how far page
    preparation may fall behind the requests before fetching waits (design D7, 026 D2).
    """

    def __init__(
        self, cap: int, backlog: int = 0, max_urls: int | None = None, *, started: int = 0
    ) -> None:
        self._tasks = asyncio.Semaphore(cap + backlog)
        self._max_urls = max_urls
        self._started = started
        self._refused: int | None = None

    def start_request(self) -> bool:
        """Counts a URL request as it starts, in flight from then on, or refuses it at the URL
        limit; called with its host's slot and the global cap held, so the count is exact."""
        if self.refuse_if_full():
            return False
        self._started += 1
        return True

    def give_back(self) -> None:
        """Uncounts a request whose URL is requested again and counts then: one that ended
        without a response during a network pause and was not recorded, or one that an outage
        re-queues. Room it frees takes back a refusal, so a URL refused at the limit is
        requested after all (design D16)."""
        self._started -= 1
        if self._refused is not None and self._started < self._refused:
            self._refused = None

    def refuse_if_full(self) -> bool:
        """Refuses a new request at the URL limit, which marks the limit reached and leaves
        the request's URL queued."""
        if self._max_urls is None or self._started < self._max_urls:
            return False
        self._refused = self._max_urls
        return True

    def limit_reached(self) -> int | None:
        """The URL limit once it has refused a request."""
        return self._refused

    async def reserve_task(self) -> None:
        """Waits for room under the global cap before a URL's task is created."""
        await self._tasks.acquire()

    def task_ended(self) -> None:
        self._tasks.release()
