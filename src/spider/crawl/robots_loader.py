"""The robots.txt loader: each origin's robots.txt, requested once in a run (020 D6, D7)."""

import asyncio

from spider.crawl.fetcher import Fetcher, FetchFailure, FetchResult, Request
from spider.crawl.politeness import RequestLimits
from spider.crawl.urls import NormalizedUrl, robots_txt_url, url_host, url_origin


class RobotsLoader:
    def __init__(self, fetcher: Fetcher, limits: RequestLimits) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._origins: dict[str, asyncio.Task[FetchResult | FetchFailure]] = {}

    async def robots_txt(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        """The response to the robots.txt request of the URL's origin, made by its first URL."""
        origin = url_origin(url)
        task = self._origins.get(origin)
        if task is None:
            task = self._origins[origin] = asyncio.create_task(self._fetch(robots_txt_url(url)))
        # A URL whose task is cancelled while it waits leaves the request to the others.
        return await asyncio.shield(task)

    async def close(self) -> None:
        for task in self._origins.values():
            task.cancel()
        await asyncio.gather(*self._origins.values(), return_exceptions=True)

    async def _fetch(self, url: NormalizedUrl) -> FetchResult | FetchFailure:
        # The host's politeness gate, but never the URL limit, which counts only URLs (D6).
        async with self._limits.host(url_host(url)), self._limits.request():
            return await self._fetcher.fetch(Request(url))
