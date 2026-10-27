"""The aiohttp Fetcher: every failed request has its code (020-add-crawl-core D8; seams 3, 4)."""

import socket
import ssl

import aiohttp
import pytest
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.client_reqrep import ConnectionKey
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from spider.crawl.fetch.fetcher import AiohttpFetcher, FetchFailure, Request, fetch_error_of
from spider.crawl.fetch.proxy import ProxyVariables
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
        result = await AiohttpFetcher(session, FakeClock(), ProxyVariables()).fetch(Request(url))

    assert (type(result), getattr(result, "fetch_error", None)) == (FetchFailure, "dns_error")


_KEY = ConnectionKey("site.test", 443, True, True, None, None, None, None)
_REQUEST = aiohttp.RequestInfo(URL("https://site.test/"), "GET", CIMultiDictProxy(CIMultiDict()))

# Every error class the Fetcher can meet, with its code: a subclass that an earlier branch of
# the mapping catches fails here, not in a Crawl.
_ERRORS: list[tuple[Exception, str]] = [
    (
        aiohttp.ClientConnectorCertificateError(_KEY, ssl.SSLCertVerificationError("self-signed")),
        "tls_error",
    ),
    (aiohttp.ClientConnectorSSLError(_KEY, ssl.SSLError("handshake failed")), "tls_error"),
    (aiohttp.ClientConnectorDNSError(_KEY, OSError("no such host")), "dns_error"),
    (UnicodeError("label empty or too long"), "dns_error"),
    (aiohttp.ClientConnectorError(_KEY, ConnectionRefusedError()), "connection_refused"),
    (aiohttp.ClientConnectorError(_KEY, OSError("network unreachable")), "connection_error"),
    (aiohttp.ClientProxyConnectionError(_KEY, OSError("proxy down")), "connection_error"),
    (aiohttp.ClientOSError(OSError("broken pipe")), "connection_error"),
    (aiohttp.ClientConnectionResetError("reset by peer"), "connection_error"),
    (aiohttp.ServerDisconnectedError(), "connection_error"),
    (aiohttp.ClientPayloadError("body cut short"), "connection_error"),
    (
        aiohttp.ClientResponseError(_REQUEST, (), status=400, message="bad status line"),
        "invalid_response",
    ),
    (aiohttp.ConnectionTimeoutError(), "timeout"),
    (aiohttp.SocketTimeoutError(), "timeout"),
    # aiohttp's total timeout, --timeout, raises a plain TimeoutError.
    (TimeoutError(), "timeout"),
    (aiohttp.InvalidURL("http://[bad"), "connection_error"),
]


@pytest.mark.parametrize(
    ("error", "fetch_error"), _ERRORS, ids=[type(error).__name__ for error, _ in _ERRORS]
)
def test_each_error_of_a_request_has_its_fetch_error(error: Exception, fetch_error: str) -> None:
    assert fetch_error_of(error) == fetch_error
