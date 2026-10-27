"""The fake Fetcher: a boundary double for timing scenarios only (020-add-crawl-core D8, D15)."""

from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from spider.clock import Clock
from spider.crawl.fetch.fetcher import FetchFailure, FetchResult, Request
from spider.store.records import FetchError


@dataclass(frozen=True, slots=True)
class FakePage:
    body: str
    content_type: str = "text/html"
    # Seconds on the clock before it answers, as a slow server takes.
    delay: float = 0.0
    # No HTTP response, with this fetch_error, until the clock's monotonic time `until`, or
    # ever when it is None: a section or a network that is down.
    fails: FetchError | None = None
    until: float | None = None


_NOT_FOUND = FakePage("")


class FakeFetcher:
    """Answers at once from `pages`, by the whole URL or else by path, so one host can differ
    from the others, and 404 for any other URL; `starts` records each request's URL and the
    clock's monotonic time when it started."""

    def __init__(
        self,
        clock: Clock,
        pages: Mapping[str, FakePage],
        *,
        outage: tuple[float, float] | None = None,
    ) -> None:
        """`outage` is a span of monotonic time in which no request started gets a response,
        whatever its URL: the network itself is down."""
        self._clock = clock
        self._pages = pages
        self._outage = outage
        self.starts: list[tuple[str, float]] = []
        self._in_flight = 0
        self.most_in_flight = 0

    @property
    def path_starts(self) -> list[tuple[str, float]]:
        """`starts` by path, for a test of one host."""
        return [(urlsplit(url).path or "/", at) for url, at in self.starts]

    async def fetch(self, request: Request) -> FetchResult | FetchFailure:
        path = urlsplit(request.url).path or "/"
        started = self._clock.monotonic()
        self.starts.append((request.url, started))
        page = self._pages.get(request.url) or self._pages.get(path)
        fails = self._fails(page, started)
        if fails is not None:
            # A failure takes the page's delay too, as a connection that times out does.
            if page is not None and page.delay:
                await self._clock.sleep(page.delay)
            return FetchFailure(
                fetch_error=fails,
                message="No HTTP response, as the test asks",
                fetched_at=self._clock.now(),
            )
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

    def _fails(self, page: FakePage | None, started: float) -> FetchError | None:
        if self._outage is not None and self._outage[0] <= started < self._outage[1]:
            return "connection_error"
        if page is None or page.fails is None:
            return None
        return page.fails if page.until is None or started < page.until else None
