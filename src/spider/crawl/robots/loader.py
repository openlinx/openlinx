"""The robots.txt loader: each origin's robots.txt, once a run (020-add-crawl-core D6, D7)."""

import asyncio
from datetime import datetime

from spider.crawl.fetch.fetcher import FetchFailure, FetchResult
from spider.crawl.fetch.requester import Requester
from spider.crawl.following import redirect_target
from spider.crawl.robots.reader import OriginRobots, read_robots_txt, robots_state, robots_txt_text
from spider.crawl.urls import NormalizedUrl, robots_txt_url, url_origin
from spider.store.origins import record_robots_txt
from spider.store.records import RobotsTxtRecord
from spider.store.writer import CrawlWriter

# RFC 9309 2.3.1.2: at least five consecutive redirects are followed.
_REDIRECT_HOPS = 5


class RobotsLoader:
    def __init__(self, requester: Requester, writer: CrawlWriter, token: str) -> None:
        self._requester = requester
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

    def requested(self, url: NormalizedUrl) -> bool:
        """Whether the robots.txt of the URL's origin needs no new request."""
        return url_origin(url) in self._origins

    async def close(self) -> None:
        for task in self._origins.values():
            task.cancel()
        await asyncio.gather(*self._origins.values(), return_exceptions=True)

    async def _load(self, robots_url: NormalizedUrl) -> OriginRobots:
        url = robots_url
        response = await self._requester.request_robots_txt(url)
        redirect: FetchResult | None = None
        # Up to five hops, as RFC 9309 asks; a longer chain ends on a 3xx, which is missing.
        for _ in range(_REDIRECT_HOPS):
            if isinstance(response, FetchFailure):
                break
            target = redirect_target(url, response.status_code, response.header("Location"), None)
            if target is None:
                break
            redirect, url = response, target
            response = await self._requester.request_robots_txt(url)
        if isinstance(response, FetchFailure) and redirect is not None:
            # The origin answered; only where it sent the request failed (design D6).
            robots, text = _failed_redirect(redirect, url, response), None
        else:
            robots, text = _origin_robots(response, self._token)
        # The URL's origin row exists: the URL that requests robots.txt was recorded first.
        record = _robots_txt_record(url_origin(robots_url), robots, text, response.fetched_at)
        await self._writer.run_async(record_robots_txt(record))
        return robots


def _failed_redirect(
    redirect: FetchResult, target: NormalizedUrl, failure: FetchFailure
) -> OriginRobots:
    return OriginRobots(
        state="missing",
        status_code=redirect.status_code,
        fetch_error=failure.fetch_error,
        fetch_error_message=failure.message,
        failed_redirect=target,
    )


def _origin_robots(
    response: FetchResult | FetchFailure, token: str
) -> tuple[OriginRobots, str | None]:
    """The origin's verdict, and the text it was read from, which only the store keeps."""
    if isinstance(response, FetchFailure):
        failed = OriginRobots(
            state="unreachable",
            fetch_error=response.fetch_error,
            fetch_error_message=response.message,
        )
        return failed, None
    state = robots_state(response.status_code)
    if state != "ok":
        return OriginRobots(state=state, status_code=response.status_code), None
    text = robots_txt_text(response.body)
    rules = read_robots_txt(text, token)
    return OriginRobots(state=state, rules=rules, status_code=response.status_code), text


def _robots_txt_record(
    origin: str, robots: OriginRobots, text: str | None, fetched_at: datetime
) -> RobotsTxtRecord:
    rules = robots.rules
    return RobotsTxtRecord(
        origin=origin,
        state=robots.state,
        status_code=robots.status_code,
        fetch_error=robots.fetch_error,
        fetch_error_message=robots.fetch_error_message,
        fetched_at=fetched_at,
        text=text,
        crawl_delay_ms=None if rules is None else rules.crawl_delay_ms,
        sitemaps=() if rules is None else rules.sitemaps,
    )
