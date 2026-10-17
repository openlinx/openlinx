"""The fake Fetcher: a boundary double for timing scenarios only (020-add-crawl-core D8, D15)."""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from spider.clock import Clock
from spider.crawl.fetcher import FetchResult, Request


@dataclass(frozen=True, slots=True)
class FakePage:
    body: str
    content_type: str = "text/html"


_NOT_FOUND = FakePage("")


class FakeFetcher:
    """Answers at once from `pages`, by path, and 404 for any other path; `starts` records each
    request's path and the clock's monotonic time when it started."""

    def __init__(self, clock: Clock, pages: Mapping[str, FakePage]) -> None:
        self._clock = clock
        self._pages = pages
        self.starts: list[tuple[str, float]] = []

    async def fetch(self, request: Request) -> FetchResult:
        path = urlsplit(request.url).path or "/"
        self.starts.append((path, self._clock.monotonic()))
        page = self._pages.get(path)
        status_code = 200 if page is not None else 404
        page = page or _NOT_FOUND
        return FetchResult(
            status_code=status_code,
            headers=(("Content-Type", page.content_type),),
            body=page.body.encode(),
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )
