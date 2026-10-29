"""The fake Fetcher: a boundary double for timing scenarios only (020-add-crawl-core D8, D15)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

from openlinx.clock import Clock
from openlinx.crawl.fetch.fetcher import FetchFailure, FetchResult, Request
from openlinx.store.records import FetchError


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
        outages: Sequence[tuple[float, float]] = (),
        on_start: Mapping[str, Callable[[], object]] | None = None,
        on_answer: Mapping[str, Callable[[], object]] | None = None,
    ) -> None:
        """`outages` are spans of monotonic time in which no request started gets a response,
        whatever its URL: the network itself is down. `on_start` runs a callback, by the whole
        URL or else by path, when its request starts, as a stop request that arrives then;
        `on_answer` runs one when its response is about to be returned."""
        self._clock = clock
        self._pages = pages
        self._outages = outages
        self._on_start = on_start or {}
        self._on_answer = on_answer or {}
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
        callback = self._on_start.get(request.url) or self._on_start.get(path)
        if callback is not None:
            callback()
        page = self._pages.get(request.url) or self._pages.get(path)
        fails = self._fails(page, started)
        status_code = 200 if page is not None else 404
        page = page or _NOT_FOUND
        self._in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self._in_flight)
        try:
            # A failure takes the page's delay too, as a connection that times out does.
            if page.delay:
                await self._clock.sleep(page.delay)
        finally:
            self._in_flight -= 1
        answered = self._on_answer.get(request.url) or self._on_answer.get(path)
        if answered is not None:
            answered()
        if fails is not None:
            return FetchFailure(
                fetch_error=fails,
                message="No HTTP response, as the test asks",
                fetched_at=self._clock.now(),
            )
        return FetchResult(
            status_code=status_code,
            reason=HTTPStatus(status_code).phrase,
            headers=(("Content-Type", page.content_type),),
            body=page.body.encode(),
            fetched_at=self._clock.now(),
            response_time_ms=0,
        )

    def _fails(self, page: FakePage | None, started: float) -> FetchError | None:
        if any(begins <= started < ends for begins, ends in self._outages):
            return "connection_error"
        if page is None or page.fails is None:
            return None
        return page.fails if page.until is None or started < page.until else None
