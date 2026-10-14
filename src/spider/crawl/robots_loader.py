"""The robots.txt loader: each origin's robots.txt, requested once in a run (020 D6, D7)."""

import asyncio

from spider.crawl.fetcher import Fetcher, FetchResult, Request
from spider.crawl.politeness import RequestLimits
from spider.crawl.robots import OriginRobots, read_robots_txt
from spider.crawl.urls import NormalizedUrl, robots_txt_url, url_host, url_origin


class RobotsLoader:
    def __init__(self, fetcher: Fetcher, limits: RequestLimits, token: str) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._token = token
        self._origins: dict[str, asyncio.Task[OriginRobots]] = {}

    async def robots_of(self, url: NormalizedUrl) -> OriginRobots:
        """The robots.txt of the URL's origin, requested by the origin's first URL."""
        origin = url_origin(url)
        task = self._origins.get(origin)
        if task is None:
            task = self._origins[origin] = asyncio.create_task(self._load(robots_txt_url(url)))
        # A URL whose task is cancelled while it waits leaves the request to the others.
        return await asyncio.shield(task)

    async def close(self) -> None:
        for task in self._origins.values():
            task.cancel()
        await asyncio.gather(*self._origins.values(), return_exceptions=True)

    async def _load(self, url: NormalizedUrl) -> OriginRobots:
        # The host's politeness gate, but never the URL limit, which counts only URLs (D6).
        async with self._limits.host(url_host(url)), self._limits.request():
            response = await self._fetcher.fetch(Request(url))
        if isinstance(response, FetchResult) and 200 <= response.status_code < 300:
            return OriginRobots(read_robots_txt(response.body, self._token))
        return OriginRobots(None)
