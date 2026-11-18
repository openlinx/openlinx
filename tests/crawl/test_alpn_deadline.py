"""Exercise the capability probe's total deadline at real network boundaries."""

import asyncio
import socket
from collections.abc import AsyncIterator, Buffer
from contextlib import AsyncExitStack, asynccontextmanager, closing, suppress
from pathlib import Path
from time import monotonic

import pytest
from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.aio import loop_factory
from openlinx.clock import Clock
from openlinx.crawl.fetch.fetcher import Fetcher, FetchPolicy, FetchResult, Request, aiohttp_fetcher
from openlinx.crawl.urls import NormalizedUrl
from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import RequestLog, ServerHandle
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.network import closed_port
from tests.support.proxy import StartProxy
from tests.support.workspace import TempWorkspace

_PROXY = "http://proxy.test:3128"


class _ProbeRoute(AbstractResolver):
    """Keep ordinary requests on the real proxy while controlling fresh DNS lookups."""

    def __init__(self, proxy_url: str, trust_anchors: str) -> None:
        self._resolver = FixtureResolver(
            {("proxy.test", 3128): ServerHandle(proxy_url, RequestLog())}
        )
        self._trust_anchors = trust_anchors
        self._primed = False
        self.probe_port: int | None = None
        self.tunnel: _StalledTunnel | None = None
        self.delay = 0.0
        self.lookups = 0
        self.dns_started: float | None = None
        self.dns_cancelled: float | None = None

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        rows = await self._resolver.resolve(host, port, family)
        if self._primed:
            self.lookups += 1
            self.dns_started = monotonic()
            try:
                if self.delay:
                    await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.dns_cancelled = monotonic()
                raise
            if self.probe_port is not None:
                rows[0]["port"] = self.probe_port
        return rows

    async def close(self) -> None:
        await self._resolver.close()

    @asynccontextmanager
    async def fetchers(self, policy: FetchPolicy, clock: Clock) -> AsyncIterator[Fetcher]:
        async with AsyncExitStack() as stack:
            if self.tunnel is not None:
                self.probe_port = await stack.enter_async_context(self.tunnel.listen())
            fetcher = await stack.enter_async_context(
                aiohttp_fetcher(policy, clock, self, self._trust_anchors)
            )
            # Normal requests use the warmed aiohttp DNS cache. The dedicated probe
            # uses the same resolver directly, so only its fresh lookup is held.
            warmup = await fetcher.fetch(
                Request(NormalizedUrl("https://site.test/_warmup"), is_internal=True)
            )
            assert isinstance(warmup, FetchResult)
            assert warmup.status_code == 404
            self._primed = True
            yield fetcher


class _StalledTunnel:
    """Observe a client closing the socket while this loopback peer withholds a reply."""

    def __init__(self, *, connect_delay: float | None, safety_timeout: float) -> None:
        self._connect_delay = connect_delay
        self._safety_timeout = safety_timeout
        self.connect_at: float | None = None
        self.tls_at: float | None = None
        self.client_closed_at: float | None = None

    @asynccontextmanager
    async def listen(self) -> AsyncIterator[int]:
        async with asyncio.TaskGroup() as handlers:

            def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                handlers.create_task(self._serve(reader, writer))

            async with await asyncio.start_server(accept, "127.0.0.1", 0) as server:
                yield int(server.sockets[0].getsockname()[1])

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            async with asyncio.timeout(self._safety_timeout):
                head = await reader.readuntil(b"\r\n\r\n")
                assert head.split(b"\r\n", 1)[0] == b"CONNECT site.test:443 HTTP/1.1"
                self.connect_at = monotonic()
                if self._connect_delay is not None:
                    if self._connect_delay:
                        # Script response latency after receiving the actual request.
                        await asyncio.sleep(self._connect_delay)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    tls_record_type = await reader.readexactly(1)
                    assert tls_record_type == b"\x16"
                    self.tls_at = monotonic()
            try:
                async with asyncio.timeout(self._safety_timeout):
                    # A connection reset and an orderly EOF both prove client closure.
                    while await reader.read(4096):
                        pass
            except ConnectionError:
                pass
            self.client_closed_at = monotonic()
        except TimeoutError:
            # A broken client must not hang the test. The assertion needs client closure.
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()


class _DelayedConnect:
    """Delay one address at asyncio's OS connect boundary, including on Windows."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, route: _ProbeRoute, seconds: float) -> None:
        self.pending: socket.socket | None = None
        self.started: float | None = None
        self.cancelled: float | None = None
        with closing(loop_factory()) as loop:
            loop_type = type(loop)
        actual_connect = loop_type.sock_connect

        async def connect(
            event_loop: asyncio.AbstractEventLoop,
            sock: socket.socket,
            target: tuple[object, ...] | str | Buffer,
        ) -> None:
            if target == ("127.0.0.1", route.probe_port):
                # Models a pending connect without relying on how the OS handles a full
                # accept backlog. Non-probe traffic still connects normally.
                self.pending = sock
                self.started = monotonic()
                try:
                    await asyncio.sleep(seconds)
                except asyncio.CancelledError:
                    self.cancelled = monotonic()
                    raise
            await actual_connect(event_loop, sock, target)

        monkeypatch.setattr(loop_type, "sock_connect", connect)


@pytest.fixture
def probe_route(fixture_tls_hosts: StartTlsHosts, fixture_proxy: StartProxy) -> _ProbeRoute:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<title>Home</title>")}), Site({}), alpn=("h2", "http/1.1")
    )
    proxy = fixture_proxy(hosts.resolver)
    return _ProbeRoute(proxy.url, hosts.trust_anchors)


def test_a_stalled_capability_probe_has_a_total_deadline(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute
) -> None:
    probe_route.delay = 2.5

    crawl_file = _crawl(probe_route)

    assert probe_route.lookups == 1
    assert probe_route.dns_started is not None
    assert probe_route.dns_cancelled is not None
    assert probe_route.dns_cancelled - probe_route.dns_started >= 0.70
    _assert_unmeasured(crawl_file)


def test_the_capability_deadline_includes_waiting_for_admission(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute
) -> None:
    # The first robots.txt request claims the origin. The next host-rate turn is
    # two seconds later, so the probe must expire without starting DNS.
    crawl_file = _crawl(probe_route, rate=0.5)

    assert probe_route.lookups == 0
    _assert_unmeasured(crawl_file)


def test_the_capability_deadline_cancels_an_incomplete_tcp_connect(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_route.probe_port = closed_port()
    tcp = _DelayedConnect(monkeypatch, probe_route, 2.5)

    crawl_file = _crawl(probe_route)

    assert probe_route.lookups == 1
    assert tcp.pending is not None
    assert tcp.started is not None
    assert tcp.cancelled is not None
    assert tcp.cancelled - tcp.started >= 0.70
    assert tcp.pending.fileno() == -1
    _assert_unmeasured(crawl_file)


def test_the_capability_deadline_closes_a_stalled_connect_socket(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute
) -> None:
    tunnel = _StalledTunnel(connect_delay=None, safety_timeout=2.5)
    probe_route.tunnel = tunnel

    crawl_file = _crawl(probe_route)

    assert tunnel.connect_at is not None
    assert tunnel.tls_at is None
    assert tunnel.client_closed_at is not None
    assert tunnel.client_closed_at - tunnel.connect_at >= 0.70
    _assert_unmeasured(crawl_file)


def test_the_capability_deadline_closes_a_stalled_tls_socket(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute
) -> None:
    tunnel = _StalledTunnel(connect_delay=0.0, safety_timeout=2.5)
    probe_route.tunnel = tunnel

    crawl_file = _crawl(probe_route)

    assert tunnel.tls_at is not None
    assert tunnel.client_closed_at is not None
    assert tunnel.client_closed_at - tunnel.tls_at >= 0.70
    _assert_unmeasured(crawl_file)


def test_capability_phases_spend_the_same_one_second_budget(
    temp_workspace: TempWorkspace, probe_route: _ProbeRoute, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_route.delay = 0.18
    tcp = _DelayedConnect(monkeypatch, probe_route, 0.10)
    tunnel = _StalledTunnel(connect_delay=0.12, safety_timeout=0.42)
    probe_route.tunnel = tunnel

    # The probe waits for the next 1/3 s host turn, then spends about 0.4 s in
    # DNS, TCP and CONNECT. Give the TLS peer time to observe client closure,
    # but cut it off before a timer starting after admission could fire.
    crawl_file = _crawl(probe_route, rate=3.0)

    assert probe_route.dns_started is not None
    assert tcp.started is not None
    assert tunnel.connect_at is not None
    assert tunnel.tls_at is not None
    assert tunnel.client_closed_at is not None
    assert tcp.started - probe_route.dns_started >= 0.15
    assert tunnel.connect_at - tcp.started >= 0.07
    assert tunnel.tls_at - tunnel.connect_at >= 0.09
    _assert_unmeasured(crawl_file)


def _crawl(route: _ProbeRoute, *, rate: float | None = None) -> Path:
    result = crawl_result(
        "https://site.test/",
        fetchers=route.fetchers,
        proxy=_PROXY,
        timeout=1.0,
        concurrency=1,
        rate=rate,
        retries=0,
        network_wait=0,
    )
    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT url, status_code, attempt_count FROM urls") == [
        ("https://site.test/", 200, 1)
    ]
    return result.crawl_file


def _assert_unmeasured(crawl_file: Path) -> None:
    assert query(crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]
