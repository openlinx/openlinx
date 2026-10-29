"""The fake Fetcher: a boundary double for timing scenarios only (020-add-crawl-core D8, D15)."""

from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from spider.clock import Clock
from spider.crawl.fetch.fetcher import FetchResult, Request


@dataclass(frozen=True, slots=True)
class FakePage:
    body: str
    content_type: str = "text/html"
    # Seconds on the clock before it answers, as a slow server takes.
    delay: float = 0.0


_NOT_FOUND = FakePage("")


class FakeFetcher:
    """Answers at once from `pages`, by the whole URL or else by path, so one host can differ
    from the others, and 404 for any other URL; `starts` records each request's path and the
    clock's monotonic time when it started."""

    def __init__(self, clock: Clock, pages: Mapping[str, FakePage]) -> None:
        self._clock = clock
        self._pages = pages
        self.starts: list[tuple[str, float]] = []
        self._in_flight = 0
        self.most_in_flight = 0

    async def fetch(self, request: Request) -> FetchResult:
        path = urlsplit(request.url).path or "/"
        self.starts.append((path, self._clock.monotonic()))
        page = self._pages.get(request.url) or self._pages.get(path)
        status_code = 200 if page is not None else 404
        page = page or _NOT_FOUND
        self._in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self._in_flight)
        try:
            if page.delay:
                await self._clock.sleep(page.delay)
        finally:
            self._in_flight -= 1
        return FetchResult(
            status_code=status_code,
            reason=HTTPStatus(status_code).phrase,
            headers=(("Content-Type", page.content_type),),
            body=page.body.encode(),
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )
