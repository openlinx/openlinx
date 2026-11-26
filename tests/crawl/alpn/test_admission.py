"""Verify that real capability probes share URL and robots.txt connection limits."""

import asyncio
import socket
from collections.abc import Awaitable, Callable

from aiohttp.abc import AbstractResolver, ResolveResult

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


class _GatedResolver(AbstractResolver):
    def __init__(
        self, resolver: AbstractResolver, before_lookup: Callable[[str], Awaitable[None]]
    ) -> None:
        self._resolver = resolver
        self._before_lookup = before_lookup

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        await self._before_lookup(host)
        return await self._resolver.resolve(host, port, family)

    async def close(self) -> None:
        await self._resolver.close()


async def _arrived_while_blocked(started: asyncio.Event) -> bool:
    # The test holds the competing work until this observation completes.
    try:
        async with asyncio.timeout(0.5):
            await started.wait()
    except TimeoutError:
        return False
    return True


def test_a_single_host_slot_cannot_deadlock_the_capability_probe(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Home</title>")}), Site({}), alpn=("h2", "http/1.1")
    )
    probe_started = asyncio.Event()
    lookups = 0
    overlap = None

    async def before_lookup(host: str) -> None:
        nonlocal lookups, overlap
        assert host == "site.test"
        lookups += 1
        if lookups == 1:
            overlap = await _arrived_while_blocked(probe_started)
        else:
            probe_started.set()

    result = crawl_result(
        "https://site.test/",
        resolver=_GatedResolver(hosts.resolver, before_lookup),
        trust_anchors=hosts.trust_anchors,
        concurrency=1,
        retries=0,
        network_wait=0,
        timeout=5,
    )

    assert result.summary.state == "completed"
    assert (lookups, overlap) == (2, False)
    assert [request.path for request in hosts.secure_site.requests] == ["/robots.txt", "/"]
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]


def test_url_connections_and_the_probe_share_the_global_cap_across_origins(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    external = [f"shop-{n}.test" for n in range(20)]
    links = "".join(f'<a href="http://{host}/item">Shop</a>' for host in external)
    site = Site({"/": Page(body=links), "/item": Page(body="<title>Item</title>")})
    hosts = fixture_tls_hosts(site, Site({}), alpn=("h2", "http/1.1"))
    resolver = FixtureResolver(
        {("site.test", 443): hosts.secure_site, **{(host, 80): hosts.site for host in external}}
    )
    nineteen_started, twenty_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    ordinary_lookups: list[str] = []
    seed_lookups = 0
    overflow = None

    async def before_lookup(host: str) -> None:
        nonlocal seed_lookups, overflow
        if host == "site.test":
            seed_lookups += 1
            if seed_lookups == 2:
                # The admitted probe occupies one of the 20 slots while the URLs queue.
                try:
                    async with asyncio.timeout(5):
                        await nineteen_started.wait()
                    overflow = await _arrived_while_blocked(twenty_started)
                finally:
                    release.set()
            return
        ordinary_lookups.append(host)
        if len(ordinary_lookups) == 19:
            nineteen_started.set()
        if len(ordinary_lookups) == 20:
            twenty_started.set()
        await release.wait()

    result = crawl_result(
        "https://site.test/",
        resolver=_GatedResolver(resolver, before_lookup),
        trust_anchors=hosts.trust_anchors,
        # The Seed's URL must be able to return its links while its probe is admitted.
        concurrency=2,
        retries=0,
        network_wait=0,
        timeout=10,
    )

    assert result.summary.state == "completed"
    assert (seed_lookups, overflow) == (2, False)
    assert sorted((request.headers["Host"], request.path) for request in hosts.site.requests) == [
        (host, path) for host in sorted(external) for path in ("/item", "/robots.txt")
    ]
    assert query(
        result.crawl_file, "SELECT status_code, count(*) FROM urls GROUP BY status_code"
    ) == [(200, 21)]
    assert query(
        result.crawl_file,
        "SELECT http_version, count(*) FROM origins GROUP BY http_version ORDER BY http_version",
    ) == [("http_1_1", 20), ("http_2", 1)]
