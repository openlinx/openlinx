"""The aiohttp Fetcher: every request failure is returned (020-add-crawl-core D8; seam 3)."""

import socket

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from spider.crawl.fetcher import AiohttpFetcher, FetchFailure, Request
from spider.crawl.urls import parse_seed
from tests.support.clock import FakeClock


class _Unencodable(AbstractResolver):
    """The system resolver's answer for a name like a..b.test: IDNA cannot encode it."""

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        raise UnicodeError("label empty or too long")

    async def close(self) -> None:
        pass


async def test_a_host_that_dns_cannot_encode_is_a_dns_error() -> None:
    url = parse_seed("http://a..b.test/")
    assert isinstance(url, str)
    connector = aiohttp.TCPConnector(resolver=_Unencodable())

    async with aiohttp.ClientSession(connector=connector) as session:
        result = await AiohttpFetcher(session, FakeClock()).fetch(Request(url))

    assert (type(result), getattr(result, "fetch_error", None)) == (FetchFailure, "dns_error")
