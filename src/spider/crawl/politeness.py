"""Politeness: how many requests may be in flight, to one host and in all (020 D7)."""

import asyncio


def global_cap(concurrency: int) -> int:
    """Bounds sockets when many External hosts are checked at once."""
    return min(100, max(20, 4 * concurrency))


class RequestLimits:
    """A semaphore per host, the global cap on requests in flight, and the bound on URL tasks.

    A task holds its permit until its unit is submitted, so `backlog` is how far page
    preparation may fall behind the requests before fetching waits (design D7, 026 D2).
    """

    def __init__(self, concurrency: int, backlog: int = 0) -> None:
        self._concurrency = concurrency
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._requests = asyncio.Semaphore(global_cap(concurrency))
        self._tasks = asyncio.Semaphore(global_cap(concurrency) + backlog)

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
