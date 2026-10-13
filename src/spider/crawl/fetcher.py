"""The Fetcher: one request, one hop, never a redirect followed (020-add-crawl-core D8)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import aiohttp
import yarl

from spider.crawl.urls import NormalizedUrl

# Fixed until 022 makes it a setting; the watchdog of design D16 outlasts it.
REQUEST_DEADLINE_SECONDS = 20


@dataclass(frozen=True, slots=True)
class Request:
    url: NormalizedUrl


@dataclass(frozen=True, slots=True)
class FetchResult:
    status_code: int


class Fetcher(Protocol):
    async def fetch(self, request: Request) -> FetchResult: ...


class AiohttpFetcher:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def fetch(self, request: Request) -> FetchResult:
        # As given: yarl would decode a %2F in the query and request another URL than recorded.
        url = yarl.URL(request.url, encoded=True)
        async with self._session.get(url, allow_redirects=False) as response:
            await response.read()
            return FetchResult(response.status)


@asynccontextmanager
async def aiohttp_fetcher() -> AsyncIterator[AiohttpFetcher]:
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=REQUEST_DEADLINE_SECONDS),
        # No cookie session: a cookie set by one response would change what later ones return.
        cookie_jar=aiohttp.DummyCookieJar(),
    ) as session:
        yield AiohttpFetcher(session)
