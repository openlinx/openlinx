"""The Fetcher: one request, one hop, never a redirect followed (020-add-crawl-core D8)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import aiohttp
import yarl

from spider.clock import Clock
from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchError

# Fixed until 022 makes it a setting; the watchdog of design D16 outlasts it.
_REQUEST_DEADLINE_SECONDS = 20


@dataclass(frozen=True, slots=True)
class Request:
    url: NormalizedUrl


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchResult:
    status_code: int
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    body: bytes
    # When the request was sent, and how long until the whole body arrived.
    fetched_at: datetime
    response_time_ms: int

    def header(self, name: str) -> str | None:
        """The first value of the header `name`, in any letter case."""
        wanted = name.lower()
        return next((value for key, value in self.headers if key.lower() == wanted), None)


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchFailure:
    """A request that got no HTTP response: returned, never raised (design D8)."""

    fetch_error: FetchError
    # The exception's type and text.
    message: str
    fetched_at: datetime


class Fetcher(Protocol):
    async def fetch(self, request: Request) -> FetchResult | FetchFailure: ...


class AiohttpFetcher:
    def __init__(self, session: aiohttp.ClientSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    async def fetch(self, request: Request) -> FetchResult | FetchFailure:
        # As given: yarl would decode a %2F in the query and request another URL than recorded.
        url = yarl.URL(request.url, encoded=True)
        fetched_at, started = self._clock.now(), self._clock.monotonic()
        try:
            async with self._session.get(url, allow_redirects=False) as response:
                body = await response.read()
                # HTTP header bytes are Latin-1 by definition; nothing is lost or refused.
                headers = tuple(
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in response.raw_headers
                )
                status_code = response.status
        # Cancellation is no Exception, so it passes through.
        except Exception as error:
            return FetchFailure(
                fetch_error=_fetch_error(error),
                message=f"{type(error).__name__}: {error}",
                fetched_at=fetched_at,
            )
        elapsed = self._clock.monotonic() - started
        return FetchResult(
            status_code=status_code,
            headers=headers,
            body=body,
            fetched_at=fetched_at,
            response_time_ms=round(elapsed * 1000),
        )


def _fetch_error(error: Exception) -> FetchError:
    # The system resolver cannot encode a name such as a..b.test, and aiohttp passes that on.
    if isinstance(error, aiohttp.ClientConnectorDNSError | UnicodeError):
        return "dns_error"
    cause = error.os_error if isinstance(error, aiohttp.ClientConnectorError) else error
    if isinstance(cause, ConnectionRefusedError):
        return "connection_refused"
    # aiohttp reports a response it cannot read as HTTP this way.
    if isinstance(error, aiohttp.ClientResponseError):
        return "invalid_response"
    return "connection_error"


@asynccontextmanager
async def aiohttp_fetcher(clock: Clock) -> AsyncIterator[AiohttpFetcher]:
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=_REQUEST_DEADLINE_SECONDS),
        # No cookie session: a cookie set by one response would change what later ones return.
        cookie_jar=aiohttp.DummyCookieJar(),
    ) as session:
        yield AiohttpFetcher(session, clock)
