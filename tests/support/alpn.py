"""Route a fresh TLS connection to a certificate for the wrong host."""

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.clock import Clock
from openlinx.crawl.fetch.fetcher import (
    Fetcher,
    FetcherFactory,
    FetchPolicy,
    FetchResult,
    Request,
    aiohttp_fetcher,
)
from openlinx.crawl.urls import normalize_url
from tests.fixture_site.tls import BADCERT_HOST, HTTPS_PORT, TlsHosts


class _ProbeRoute(AbstractResolver):
    def __init__(self, hosts: TlsHosts) -> None:
        self._resolver = hosts.resolver
        self.to_wrong_name = False

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        if self.to_wrong_name and (host, port) == ("site.test", HTTPS_PORT):
            rows = await self._resolver.resolve(BADCERT_HOST, port, family)
            for row in rows:
                row["hostname"] = host
            return rows
        return await self._resolver.resolve(host, port, family)

    async def close(self) -> None:
        await self._resolver.close()


def with_wrong_name_for_probe(hosts: TlsHosts) -> FetcherFactory:
    """Prime the ordinary session's DNS route before a fresh lookup is sent elsewhere."""

    @asynccontextmanager
    async def start(policy: FetchPolicy, clock: Clock) -> AsyncIterator[Fetcher]:
        resolver = _ProbeRoute(hosts)
        async with aiohttp_fetcher(policy, clock, resolver, hosts.trust_anchors) as fetcher:
            control = normalize_url("https://site.test/_warmup")
            assert isinstance(control, str)
            response = await fetcher.fetch(Request(control, is_internal=True))
            assert isinstance(response, FetchResult)
            assert response.status_code == 404
            # The regular requests keep their cached address, even over new pooled connections.
            resolver.to_wrong_name = True
            yield fetcher

    return start
