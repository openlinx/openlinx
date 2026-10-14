"""The robots.txt loader: each origin's robots.txt, requested once in a run (020 D6, D7)."""

import asyncio

from spider.crawl.fetcher import Fetcher, FetchResult, Request
from spider.crawl.politeness import RequestLimits
from spider.crawl.robots import OriginRobots, read_robots_txt, robots_state
from spider.crawl.urls import NormalizedUrl, robots_txt_url, url_host, url_origin
from spider.store.origins import record_robots_txt
from spider.store.records import RobotsTxtRecord
from spider.store.writer import CrawlWriter


class RobotsLoader:
    def __init__(
        self, fetcher: Fetcher, limits: RequestLimits, writer: CrawlWriter, token: str
    ) -> None:
        self._fetcher = fetcher
        self._limits = limits
        self._writer = writer
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
        if not isinstance(response, FetchResult):
            return OriginRobots(None)
        state = robots_state(response.status_code)
        rules = read_robots_txt(response.body, self._token) if state == "ok" else None
        record = RobotsTxtRecord(
            # The URL's origin row exists: the URL that requests robots.txt was recorded first.
            origin=url_origin(url),
            state=state,
            status_code=response.status_code,
            fetched_at=response.fetched_at,
            text=None if rules is None else rules.text,
            crawl_delay_ms=None if rules is None else rules.crawl_delay_ms,
            sitemaps=() if rules is None else rules.sitemaps,
        )
        await self._writer.run_async(record_robots_txt(record))
        return OriginRobots(
            rules, unreachable=state == "unreachable", status_code=response.status_code
        )
