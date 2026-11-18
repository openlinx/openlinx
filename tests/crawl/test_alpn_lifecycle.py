"""Verify ALPN cancellation and joining through the Crawl Service and loopback sockets."""

import asyncio
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager, asynccontextmanager, suppress
from datetime import datetime

from aiohttp.abc import AbstractResolver, ResolveResult

from openlinx.clock import Clock, SystemClock
from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext, UrlResult, handler
from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.fetch.fetcher import Fetcher, FetchPolicy, aiohttp_fetcher
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides, continue_crawl
from openlinx.store.pages import write_pages
from openlinx.store.records import CrawlFile
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


class _ObservedResolver(AbstractResolver):
    def __init__(
        self,
        resolver: AbstractResolver,
        on_lookup: Callable[[int, list[ResolveResult]], Awaitable[list[ResolveResult]]],
    ) -> None:
        self.count = 0
        self._resolver = resolver
        self._on_lookup = on_lookup

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        self.count += 1
        lookup = self.count
        addresses = await self._resolver.resolve(host, port, family)
        return await self._on_lookup(lookup, addresses)

    async def close(self) -> None:
        await self._resolver.close()


class _ObservedClock:
    """Keep wall time while exposing the 30-second probe deadline at the Clock seam."""

    def __init__(self) -> None:
        self._clock = SystemClock()
        self.deadline_started = asyncio.Event()
        self.deadline_cancelled = asyncio.Event()

    def now(self) -> datetime:
        return self._clock.now()

    def monotonic(self) -> float:
        return self._clock.monotonic()

    def off_loop(self) -> AbstractContextManager[None]:
        return self._clock.off_loop()

    async def sleep(self, seconds: float) -> None:
        deadline = 20 < seconds <= 30
        if deadline:
            self.deadline_started.set()
        try:
            await self._clock.sleep(seconds)
        except asyncio.CancelledError:
            if deadline:
                self.deadline_cancelled.set()
            raise


async def _seen(event: asyncio.Event, seconds: float) -> bool:
    try:
        async with asyncio.timeout(seconds):
            await event.wait()
    except TimeoutError:
        return False
    return True


def test_stop_closes_an_admitted_capability_probe(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    site = Site({"/": Page(body='<a href="/later">Later</a>'), "/later": Page(body="<p>Later</p>")})
    hosts = fixture_tls_hosts(site, Site({}), alpn=("h2", "http/1.1"))
    stopped = crawl_result(
        "https://site.test/",
        resolver=hosts.resolver,
        trust_anchors=hosts.trust_anchors,
        concurrency=1,
        max_urls=1,
        retries=0,
        network_wait=0,
        timeout=10,
    )
    assert (stopped.summary.state, stopped.summary.stop_reason) == ("stopped", "max_urls")
    stop = StopSignal()
    peer_closed = asyncio.Event()
    probe_tasks: list[asyncio.Task[object]] = []
    handshakes: list[bytes] = []
    before_writer_closes: list[tuple[bool, bool, bool]] = []

    @asynccontextmanager
    async def fetchers(policy: FetchPolicy, clock: Clock) -> AsyncIterator[Fetcher]:
        connected: asyncio.Future[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = (
            asyncio.get_running_loop().create_future()
        )

        def accepted(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            connected.set_result((reader, writer))

        async def wait_for_client() -> None:
            reader, writer = await connected
            try:
                handshakes.append(await reader.readexactly(1))
                stop.set("requested")
                with suppress(ConnectionResetError):
                    await reader.read()
                peer_closed.set()
            finally:
                writer.close()
                with suppress(ConnectionResetError):
                    await writer.wait_closed()

        async with await asyncio.start_server(accepted, "127.0.0.1", 0) as listener:
            observed = asyncio.create_task(wait_for_client())
            address_port = listener.sockets[0].getsockname()[1]

            async def route_probe(
                lookup: int, addresses: list[ResolveResult]
            ) -> list[ResolveResult]:
                if lookup == 1:
                    return addresses
                task = asyncio.current_task()
                assert task is not None
                probe_tasks.append(task)
                return [{**address, "port": address_port} for address in addresses]

            resolver = _ObservedResolver(hosts.resolver, route_probe)
            try:
                async with aiohttp_fetcher(
                    policy, clock, resolver=resolver, trust_anchors=hosts.trust_anchors
                ) as fetcher:
                    yield fetcher
            finally:
                observed.cancel()
                await asyncio.gather(observed, return_exceptions=True)

    async def observe(_context: PassContext) -> None:
        (task,) = probe_tasks
        before_writer_closes.append((task.done(), task.cancelled(), await _seen(peer_closed, 2)))

    result = continue_crawl(
        CrawlFile(stopped.crawl_id, stopped.crawl_file),
        CrawlOverrides(max_urls=None),
        SystemClock(),
        Collected(),
        Hooks(passes=(Pass("observe_probe_shutdown", observe),)),
        fetchers=fetchers,
        stop=stop,
    )

    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "requested")
    assert handshakes == [b"\x16"]
    assert before_writer_closes == [(True, True, True)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_stop_cancels_the_capability_probe_while_it_waits_for_admission(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(Site({"/": Page(body="<p>Seed</p>")}), Site({}), alpn=("h2",))
    stop, clock = StopSignal(), _ObservedClock()
    while_robots_held: list[tuple[bool, bool]] = []

    async def hold_robots(lookup: int, addresses: list[ResolveResult]) -> list[ResolveResult]:
        if lookup == 1:
            scheduled = await _seen(clock.deadline_started, 3)
            stop.set("requested")
            cancelled = await _seen(clock.deadline_cancelled, 2)
            while_robots_held.append((scheduled, cancelled))
        return addresses

    resolver = _ObservedResolver(hosts.resolver, hold_robots)
    result = crawl_result(
        "https://site.test/",
        resolver=resolver,
        trust_anchors=hosts.trust_anchors,
        stop=stop,
        clock=clock,
        concurrency=1,
        retries=0,
        network_wait=0,
        timeout=30,
    )

    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "requested")
    assert while_robots_held == [(True, True)]
    assert resolver.count == 1
    assert [request.path for request in hosts.secure_site.requests] == ["/robots.txt"]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_stop_joins_capability_probe_cleanup_before_its_passes(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(Site({"/": Page(body="<p>Seed</p>")}), Site({}), alpn=("h2",))
    stop = StopSignal()
    pass_started, cleanup_started, cleanup_finished = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    probe_tasks: list[asyncio.Task[object]] = []
    before_writer_closes: list[tuple[bool, bool, bool]] = []

    async def slow_cleanup(lookup: int, addresses: list[ResolveResult]) -> list[ResolveResult]:
        if lookup == 1:
            # Keep robots.txt in flight until the probe is already handling cancellation.
            async with asyncio.timeout(5):
                await cleanup_started.wait()
        else:
            task = asyncio.current_task()
            assert task is not None
            probe_tasks.append(task)
            stop.set("requested")
            try:
                await asyncio.Future[None]()
            finally:
                # An asynchronous resolver can still own resources after receiving cancellation.
                cleanup_started.set()
                if not await _seen(pass_started, 1):
                    cleanup_finished.set()
        return addresses

    async def observe(_context: PassContext) -> None:
        (task,) = probe_tasks
        before_writer_closes.append((task.done(), task.cancelled(), cleanup_finished.is_set()))
        pass_started.set()

    result = crawl_result(
        "https://site.test/",
        Hooks(passes=(Pass("observe_probe_cleanup", observe),)),
        resolver=_ObservedResolver(hosts.resolver, slow_cleanup),
        trust_anchors=hosts.trust_anchors,
        stop=stop,
        concurrency=2,
        retries=0,
        network_wait=0,
        timeout=10,
    )

    assert (result.summary.state, result.summary.stop_reason) == ("stopped", "requested")
    assert before_writer_closes == [(True, True, True)]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", None)
    ]


def test_normal_completion_joins_the_pending_capability_probe_before_its_passes(
    temp_workspace: TempWorkspace, fixture_tls_hosts: StartTlsHosts
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<p>Seed</p>")}), Site({}), alpn=("h2", "http/1.1")
    )
    seed_finished, pass_started = asyncio.Event(), asyncio.Event()
    probe_tasks: list[asyncio.Task[object]] = []
    pass_overtook_probe: list[bool] = []
    joined_at_pass: list[tuple[bool, bool]] = []

    def seed_result(result: UrlResult) -> tuple[()]:
        if result.response is not None and result.response.status_code == 200:
            seed_finished.set()
        return ()

    async def hold_probe(lookup: int, addresses: list[ResolveResult]) -> list[ResolveResult]:
        if lookup == 2:
            task = asyncio.current_task()
            assert task is not None
            probe_tasks.append(task)
            async with asyncio.timeout(5):
                await seed_finished.wait()
            pass_overtook_probe.append(await _seen(pass_started, 0.5))
        return addresses

    async def observe(_context: PassContext) -> None:
        pass_started.set()
        joined_at_pass.extend((task.done(), task.cancelled()) for task in probe_tasks)

    result = crawl_result(
        "https://site.test/",
        Hooks(
            handlers=(handler("observe_seed", seed_result, write_pages),),
            passes=(Pass("observe_probe_join", observe),),
        ),
        resolver=_ObservedResolver(hosts.resolver, hold_probe),
        trust_anchors=hosts.trust_anchors,
        concurrency=2,
        retries=0,
        network_wait=0,
        timeout=10,
    )

    assert result.summary.state == "completed"
    assert (pass_overtook_probe, joined_at_pass) == ([False], [(True, False)])
    assert query(result.crawl_file, "SELECT url, status_code FROM urls") == [
        ("https://site.test/", 200)
    ]
    assert query(result.crawl_file, "SELECT origin, http_version FROM origins") == [
        ("https://site.test", "http_2")
    ]
