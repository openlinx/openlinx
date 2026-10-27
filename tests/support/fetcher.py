"""The fake Fetcher: a boundary double for timing scenarios only (020-add-crawl-core D8, D15)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from spider.clock import Clock
from spider.crawl.fetch.fetcher import FetchResult, Request


@dataclass(frozen=True, slots=True)
class FakePage:
    body: str
    content_type: str = "text/html"
    status: int = 200
    headers: tuple[tuple[str, str], ...] = ()
    # Seconds on the clock before it answers, as a slow server takes.
    delay: float = 0.0


_NOT_FOUND = FakePage("", status=404)


class FakeFetcher:
    """Answers from `pages`, by the whole URL or else by path, so one host can differ from the
    others, after the page's delay, and 404 for any other URL; a sequence of pages answers in
    turn, one per request, then repeats its last. `starts` records each request's path and the
    clock's monotonic time when it started."""

    def __init__(self, clock: Clock, pages: Mapping[str, FakePage | Sequence[FakePage]]) -> None:
        if any(not isinstance(page, FakePage) and not page for page in pages.values()):
            raise ValueError("a sequence of fake pages takes at least one page")
        self._clock = clock
        self._pages = pages
        self._answered: dict[str, int] = {}
        self.starts: list[tuple[str, float]] = []
        self._in_flight = 0
        self.most_in_flight = 0

    async def fetch(self, request: Request) -> FetchResult:
        path = urlsplit(request.url).path or "/"
        self.starts.append((path, self._clock.monotonic()))
        page = self._page(request.url if request.url in self._pages else path)
        self._in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self._in_flight)
        try:
            if page.delay:
                await self._clock.sleep(page.delay)
        finally:
            self._in_flight -= 1
        return FetchResult(
            status_code=page.status,
            reason=HTTPStatus(page.status).phrase,
            headers=(("Content-Type", page.content_type), *page.headers),
            body=page.body.encode(),
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )

    def _page(self, key: str) -> FakePage:
        found = self._pages.get(key, _NOT_FOUND)
        if isinstance(found, FakePage):
            return found
        count = self._answered.get(key, 0)
        self._answered[key] = count + 1
        return found[min(count, len(found) - 1)]
