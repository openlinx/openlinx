"""Apply host timing, concurrency and URL limits before requests start."""

import asyncio

from openlinx.clock import Clock
from openlinx.crawl.urls import NormalizedUrl, host_key


class RateGate:
    """--rate: requests to one host start at least 1/rate seconds apart, on the clock; and a
    host's pause, after a 429 or a Retry-After, before which none of its requests starts, with
    or without --rate (022-add-fetch-policy D4)."""

    def __init__(self, clock: Clock, rate: float | None) -> None:
        self._clock = clock
        self._interval = None if rate is None else 1 / rate
        self._next_starts: dict[str, float] = {}
        self._last_starts: dict[str, float] = {}
        self._paused_until: dict[str, float] = {}

    def pause(self, host: str, seconds: float) -> None:
        until = self._clock.monotonic() + seconds
        self._paused_until[host] = max(until, self._paused_until.get(host, until))

    def reserve_turn(self, host: str) -> float:
        """The seconds until the host's next turn, which is the caller's from now on."""
        now = self._clock.monotonic()
        resume = max(now, self._paused_until.get(host, now))
        if self._interval is None:
            return resume - now
        start = max(resume, self._next_starts.get(host, now))
        # Reserved before the wait, so the host's waiters take turns in order, and hold no
        # lock that would make one host's wait another's.
        self._next_starts[host] = start + self._interval
        return start - now

    def pause_left(self, host: str) -> float:
        """The seconds left of the host's pause."""
        return max(0.0, self._paused_until.get(host, 0.0) - self._clock.monotonic())

    async def started(self, host: str) -> None:
        """With the global permit held and the host's pause over: waits out what is left of the
        interval since the host's last start, which only a wait for the permit leaves."""
        if self._interval is None:
            return
        now = self._clock.monotonic()
        last = self._last_starts.get(host)
        start = now if last is None else max(now, last + self._interval)
        # Taken before the wait, so the next caller counts from this start.
        self._last_starts[host] = start
        if start > now:
            await self._clock.sleep(start - now)


def global_cap(concurrency: int) -> int:
    """Bounds sockets when many External hosts are checked at once."""
    return min(100, max(20, 4 * concurrency))


class RequestLimits:
    """The bound on URL tasks and the URL limit, --max-urls, which counts every request it lets
    start; the Requester holds the hosts' slots and the global cap.

    A task holds room until submitting its unit. With a preparation backlog, the
    same lifetime also counts against its host's task bound, since the host's
    request slot is free once HTTP ends, before preparation (026-add-parse-pool D2)."""

    def __init__(
        self, concurrency: int, backlog: int = 0, max_urls: int | None = None, *, started: int = 0
    ) -> None:
        self._tasks = asyncio.Semaphore(global_cap(concurrency) + backlog)
        self._host_cap = concurrency + backlog if backlog else None
        self._hosts: dict[str, int] = {}
        self._task_ended = asyncio.Event()
        self._max_urls = max_urls
        self._started = started
        self._refused: int | None = None
        self._refusal = asyncio.Event()

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
        requested after all."""
        self._started -= 1
        if self._refused is not None and self._started < self._refused:
            self._refused = None
            self._refusal.clear()

    def refuse_if_full(self) -> bool:
        """Refuses a new request at the URL limit, which marks the limit reached and leaves
        the request's URL queued."""
        if self._max_urls is None or self._started < self._max_urls:
            return False
        self._refused = self._max_urls
        self._refusal.set()
        return True

    async def refused(self) -> None:
        """Returns once the URL limit has refused a request, a refusal taken back aside."""
        await self._refusal.wait()

    def limit_reached(self) -> int | None:
        """The URL limit once it has refused a request."""
        return self._refused

    def task_host(self, url: NormalizedUrl) -> str | None:
        return host_key(url) if self._host_cap is not None else None

    def host_full(self, host: str | None) -> bool:
        return host is not None and self._hosts.get(host, 0) == self._host_cap

    def watch_task_ends(self) -> asyncio.Event:
        """The dispatcher watches for task endings since the start of its pass."""
        self._task_ended.clear()
        return self._task_ended

    async def reserve_task(self, host: str | None) -> None:
        """The single dispatcher has checked host room; wait for global room before
        reserving both for a new task."""
        await self._tasks.acquire()
        if host is not None:
            self._hosts[host] = self._hosts.get(host, 0) + 1

    def task_ended(self, host: str | None) -> None:
        if host is not None:
            left = self._hosts[host] - 1
            if left:
                self._hosts[host] = left
            else:
                del self._hosts[host]
            self._task_ended.set()
        self._tasks.release()
