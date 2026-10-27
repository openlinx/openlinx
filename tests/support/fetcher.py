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


_NOT_FOUND = FakePage("", status=404)


class FakeFetcher:
    """Answers at once from `pages`, by path, and 404 for any other path; a sequence of pages
    answers in turn, one per request, then repeats its last. `starts` records each request's
    path and the clock's monotonic time when it started."""

    def __init__(self, clock: Clock, pages: Mapping[str, FakePage | Sequence[FakePage]]) -> None:
        if any(not isinstance(page, FakePage) and not page for page in pages.values()):
            raise ValueError("a sequence of fake pages takes at least one page")
        self._clock = clock
        self._pages = pages
        self._answered: dict[str, int] = {}
        self.starts: list[tuple[str, float]] = []

    async def fetch(self, request: Request) -> FetchResult:
        path = urlsplit(request.url).path or "/"
        self.starts.append((path, self._clock.monotonic()))
        page = self._page(path)
        return FetchResult(
            status_code=page.status,
            reason=HTTPStatus(page.status).phrase,
            headers=(("Content-Type", page.content_type), *page.headers),
            body=page.body.encode(),
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )

    def _page(self, path: str) -> FakePage:
        found = self._pages.get(path, _NOT_FOUND)
        if isinstance(found, FakePage):
            return found
        count = self._answered.get(path, 0)
        self._answered[path] = count + 1
        return found[min(count, len(found) - 1)]
