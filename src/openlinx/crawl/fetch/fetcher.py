"""Fetch one HTTP hop and return request failures as data."""

from base64 import b64encode
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import aiohttp
import yarl
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver

from openlinx import __version__
from openlinx.clock import Clock
from openlinx.crawl.fetch.alpn import AlpnProbe
from openlinx.crawl.fetch.body import BodyDecodingError, read_body
from openlinx.crawl.fetch.cookies import redacted_header
from openlinx.crawl.fetch.proxy import ProxyVariables
from openlinx.crawl.fetch.tls import tls_context
from openlinx.crawl.urls import NormalizedUrl
from openlinx.naming import CRAWLER_PAGE_URL, PRODUCT_NAME
from openlinx.store.records import FetchError, HttpVersion


def header_values(headers: Iterable[tuple[str, str]], name: str) -> list[str]:
    """The values of the header `name`, in any letter case, in the order received."""
    wanted = name.lower()
    return [value for key, value in headers if key.lower() == wanted]


def joined_header(headers: Iterable[tuple[str, str]], name: str) -> str | None:
    """The header `name` with its repeated lines joined into one list, as RFC 9110 5.3
    reads them; None without one."""
    values = header_values(headers, name)
    return ", ".join(values) if values else None


def _received_header(name: bytes, value: bytes) -> tuple[str, str]:
    # HTTP header bytes are Latin-1 by definition; nothing is lost or refused.
    text = name.decode("latin-1")
    return text, redacted_header(text, value.decode("latin-1"))


@dataclass(frozen=True, slots=True)
class Request:
    url: NormalizedUrl
    is_internal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchResult:
    status_code: int
    reason: str | None
    # As received, cookie values redacted (openlinx.crawl.fetch.cookies): in order, in their letter
    # case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    body: bytes
    # When the request was sent, and how long until the whole body arrived.
    fetched_at: datetime
    response_time_ms: int
    # Larger than the body cap, so read only up to it.
    body_truncated: bool = False
    # The bytes read before decoding; None from a fake Fetcher, which sends its body as is.
    transferred_bytes: int | None = None

    def header(self, name: str) -> str | None:
        """The first value of the header `name`, in any letter case."""
        return next(iter(header_values(self.headers, name)), None)


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchFailure:
    """A request that got no HTTP response: returned, never raised."""

    fetch_error: FetchError
    # The exception's type and text.
    message: str
    fetched_at: datetime


class Fetcher(Protocol):
    async def fetch(self, request: Request) -> FetchResult | FetchFailure: ...


@runtime_checkable
class ProbesHttpVersion(Protocol):
    @property
    def probe_http_version(self) -> Callable[[str], Awaitable[HttpVersion | None]] | None: ...


_CHUNK_BYTES = 64 * 1024
ACCEPT_ENCODING = "gzip, deflate, br, zstd"
DEFAULT_USER_AGENT = f"{PRODUCT_NAME}/{__version__} (+{CRAWLER_PAGE_URL})"


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchPolicy:
    """The Fetcher's settings of a Crawl, from its plan to its Fetcher; retries and the hop limit
    are the Requester's and the engine's."""

    user_agent: str
    proxies: ProxyVariables
    # The request watchdog outlasts this deadline, so it does not cut the Fetcher short.
    timeout_seconds: float
    headers: tuple[tuple[str, str], ...] = ()
    custom_user_agent: bool = False
    auth: str | None = None
    proxy: str | None = None

    def proxy_for(self, url: str) -> str | None:
        return self.proxy or self.proxies.for_url(url)


def request_headers(policy: FetchPolicy, *, is_internal: bool) -> tuple[tuple[str, str], ...]:
    custom = policy.headers if is_internal else ()
    headers = tuple(
        (name, value)
        for name, value in custom
        if name.lower() != "user-agent" or policy.custom_user_agent
    )
    if not (is_internal and policy.custom_user_agent):
        headers = (("User-Agent", policy.user_agent), *headers)
    if not any(name.lower() == "accept-encoding" for name, _ in headers):
        headers = (*headers, ("Accept-Encoding", ACCEPT_ENCODING))
    if is_internal and policy.auth:
        authorization = "Basic " + b64encode(policy.auth.encode("utf-8")).decode("ascii")
        headers = (*headers, ("Authorization", authorization))
    # aiohttp merges repeated input names case-sensitively before writing them.
    return tuple((name.lower(), value) for name, value in headers)


# Opens the Crawl's Fetcher: tests bind the DNS resolver hook or a fake Fetcher into one.
type FetcherFactory = Callable[[FetchPolicy, Clock], AbstractAsyncContextManager[Fetcher]]


class AiohttpFetcher:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        clock: Clock,
        policy: FetchPolicy,
        alpn: AlpnProbe | None = None,
    ) -> None:
        self._session = session
        self._clock = clock
        self._policy = policy
        self.probe_http_version = alpn.measure if alpn is not None else None

    async def fetch(self, request: Request) -> FetchResult | FetchFailure:
        # As given: yarl would decode a %2F in the query and request another URL than recorded.
        url = yarl.URL(request.url, encoded=True)
        fetched_at, started = self._clock.now(), self._clock.monotonic()
        try:
            async with self._session.get(
                url,
                allow_redirects=False,
                proxy=self._policy.proxy_for(request.url),
                headers=request_headers(self._policy, is_internal=request.is_internal),
            ) as response:
                headers = tuple(
                    _received_header(name, value) for name, value in response.raw_headers
                )
                body = await read_body(
                    response.content.iter_chunked(_CHUNK_BYTES),
                    joined_header(headers, "Content-Encoding"),
                )
                status_code, reason = response.status, response.reason
        # Cancellation is no Exception, so it passes through.
        except Exception as error:
            return FetchFailure(
                fetch_error=fetch_error_of(error),
                message=f"{type(error).__name__}: {error}",
                fetched_at=fetched_at,
            )
        elapsed = self._clock.monotonic() - started
        return FetchResult(
            status_code=status_code,
            reason=reason,
            headers=headers,
            body=body.data,
            fetched_at=fetched_at,
            response_time_ms=round(elapsed * 1000),
            body_truncated=body.truncated,
            transferred_bytes=body.transferred_bytes,
        )


def fetch_error_of(error: Exception) -> FetchError:
    # First: aiohttp's TLS errors are ClientConnectorErrors too, and a certificate failure is
    # an answer of sorts, which the network pause must never count (020-add-crawl-core D16).
    if isinstance(error, aiohttp.ClientSSLError):
        return "tls_error"
    if isinstance(error, BodyDecodingError):
        return "invalid_response"
    # The system resolver cannot encode a name such as a..b.test, and aiohttp passes that on.
    if isinstance(error, aiohttp.ClientConnectorDNSError | UnicodeError):
        return "dns_error"
    cause = error.os_error if isinstance(error, aiohttp.ClientConnectorError) else error
    if isinstance(cause, ConnectionRefusedError):
        return "connection_refused"
    # aiohttp reports a response it cannot read as HTTP this way.
    if isinstance(error, aiohttp.ClientResponseError):
        return "invalid_response"
    # aiohttp's connect and read timeouts derive from TimeoutError, as its total timeout raises;
    # the OS's own connect timeout (ETIMEDOUT) comes wrapped in a connector error.
    if isinstance(cause, TimeoutError):
        return "timeout"
    return "connection_error"


@asynccontextmanager
async def aiohttp_fetcher(
    policy: FetchPolicy,
    clock: Clock,
    resolver: AbstractResolver | None = None,
    trust_anchors: str | None = None,
) -> AsyncIterator[AiohttpFetcher]:
    """`resolver` and `trust_anchors` (PEM certificates trusted besides the OS store) are for
    tests: the DNS resolver hook and the test CA."""
    async with AsyncExitStack() as stack:
        if resolver is None:
            resolver = DefaultResolver()
            stack.push_async_callback(resolver.close)
        session = await stack.enter_async_context(
            aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(resolver=resolver, ssl=tls_context(trust_anchors)),
                timeout=aiohttp.ClientTimeout(total=policy.timeout_seconds),
                skip_auto_headers={"User-Agent", "Accept-Encoding"},
                # A cookie set by one response must not change what later ones return.
                cookie_jar=aiohttp.DummyCookieJar(),
                # read_body measures the body both as transferred and as decoded.
                auto_decompress=False,
            )
        )
        yield AiohttpFetcher(
            session,
            clock,
            policy,
            AlpnProbe(resolver, trust_anchors, policy.timeout_seconds, policy.proxy_for),
        )
