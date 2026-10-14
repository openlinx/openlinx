"""Politeness: how many requests may be in flight, to one host and in all (020 D7)."""

import asyncio


def global_cap(concurrency: int) -> int:
    """Bounds sockets when many External hosts are checked at once."""
    return min(100, max(20, 4 * concurrency))


class RequestLimits:
    """A semaphore per host, and the global cap on the URL tasks in flight."""

    def __init__(self, concurrency: int) -> None:
        self._concurrency = concurrency
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self.tasks = asyncio.Semaphore(global_cap(concurrency))

    def host(self, host: str) -> asyncio.Semaphore:
        semaphore = self._hosts.get(host)
        if semaphore is None:
            semaphore = self._hosts[host] = asyncio.Semaphore(self._concurrency)
        return semaphore
