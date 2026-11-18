"""Measure HTTPS capability with a verified TLS handshake and no origin HTTP traffic."""

import asyncio
import socket
import ssl
from collections.abc import Callable
from contextlib import suppress
from ipaddress import ip_address

import yarl
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.helpers import is_ip_address

from openlinx.crawl.fetch.proxy_connect import CONNECT_STREAM_LIMIT, establish_tunnel
from openlinx.crawl.fetch.system_dns import resolve_system
from openlinx.crawl.fetch.tls import tls_context
from openlinx.store.records import HttpVersion


class AlpnProbe:
    def __init__(
        self,
        resolver: AbstractResolver | None,
        trust_anchors: str | None,
        timeout_seconds: float,
        proxy_for: Callable[[str], str | None],
        *,
        proxy_tls: ssl.SSLContext,
    ) -> None:
        self._resolver = resolver
        self._trust_anchors = trust_anchors
        self._timeout_seconds = timeout_seconds
        self._proxy_for = proxy_for
        self._proxy_tls = proxy_tls
        self._context: ssl.SSLContext | None = None

    async def measure(self, origin: str) -> HttpVersion | None:
        url = yarl.URL(origin, encoded=True)
        host, port = url.raw_host, url.port
        if host is None or port is None or url.scheme != "https":
            raise RuntimeError("An ALPN probe needs an HTTPS origin")
        if self._context is None:
            self._context = tls_context(self._trust_anchors)
            self._context.set_alpn_protocols(["h2", "http/1.1"])
        if (route := self._proxy_for(origin)) is not None:
            return await self._measure_proxy(route, host, port, self._context)
        try:
            addresses = await self._addresses(host, port)
        except (OSError, UnicodeError):
            return None
        for address in addresses:
            try:
                _, writer = await asyncio.open_connection(
                    address["host"],
                    address["port"],
                    family=address["family"],
                    flags=socket.AI_NUMERICHOST,
                    server_hostname=host.rstrip("."),
                    ssl=self._context,
                    ssl_handshake_timeout=self._timeout_seconds,
                )
            except OSError:
                continue
            try:
                return _version(writer)
            finally:
                await _close(writer)
        return None

    async def _measure_proxy(
        self, route: str, host: str, port: int, context: ssl.SSLContext
    ) -> HttpVersion | None:
        try:
            proxy = yarl.URL(route)
            proxy_host, proxy_port = proxy.raw_host, proxy.port
            if proxy.scheme not in {"http", "https"} or not proxy_host or proxy_port is None:
                return None
            addresses = await self._addresses(proxy_host, proxy_port)
        except (OSError, ValueError):
            return None
        # The proxy and the origin are separate TLS peers. Offer ALPN only to the origin.
        proxy_tls = self._proxy_tls if proxy.scheme == "https" else None
        for address in addresses:
            try:
                reader, writer = await asyncio.open_connection(
                    address["host"],
                    address["port"],
                    family=address["family"],
                    flags=socket.AI_NUMERICHOST,
                    limit=CONNECT_STREAM_LIMIT,
                    ssl=proxy_tls,
                    server_hostname=proxy_host.rstrip(".") if proxy_tls is not None else None,
                    ssl_handshake_timeout=self._timeout_seconds if proxy_tls is not None else None,
                )
            except OSError:
                continue
            upgrading = False
            try:
                if not await establish_tunnel(reader, writer, proxy, host, port):
                    return None
                upgrading = True
                await writer.start_tls(
                    context,
                    server_hostname=host.rstrip("."),
                    ssl_handshake_timeout=self._timeout_seconds,
                )
                upgrading = False
                return _version(writer)
            except (OSError, ValueError):
                return None
            finally:
                await _close(writer, wait=not upgrading)
        return None

    async def _addresses(self, host: str, port: int) -> list[ResolveResult]:
        if not is_ip_address(host):
            if self._resolver is None:
                return await resolve_system(host, port)
            return await self._resolver.resolve(host, port, family=socket.AF_UNSPEC)
        # Match aiohttp's literal routing and rejection of noncanonical numeric IPv4.
        try:
            address = ip_address(host)
        except ValueError:
            return []
        return [
            ResolveResult(
                hostname=host,
                host=host,
                port=port,
                family=socket.AF_INET if address.version == 4 else socket.AF_INET6,
                proto=0,
                flags=socket.AI_NUMERICHOST,
            )
        ]


def _version(writer: asyncio.StreamWriter) -> HttpVersion:
    tls = writer.get_extra_info("ssl_object")
    if not isinstance(tls, ssl.SSLObject):
        raise RuntimeError("A TLS stream must have an SSL object")
    return "http_2" if tls.selected_alpn_protocol() == "h2" else "http_1_1"


async def _close(writer: asyncio.StreamWriter, *, wait: bool = True) -> None:
    # There is no application data to flush. Don't wait for a peer's TLS shutdown.
    writer.transport.abort()
    # An interrupted start_tls can close the transport without notifying the old stream.
    if wait:
        with suppress(OSError):
            await writer.wait_closed()
