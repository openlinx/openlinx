"""Exercise the default resolver and real process ownership through Crawl shutdown."""

import asyncio
import os
import socket
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psutil
import pytest

from openlinx.clock import Clock
from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext
from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.fetch.fetcher import Fetcher, FetchPolicy, aiohttp_fetcher
from openlinx.crawl.fetch.system_dns import resolve_system
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# Run the real worker, with the same loopback mapping at the OS DNS boundary as the parent.
_WORKER_DNS = """
import os
import runpy
import socket
import sys
import threading
from pathlib import Path

marker, outcome, *sys.argv = sys.argv[1:]
native = socket.getaddrinfo

def getaddrinfo(host, *args, **kwargs):
    if host != "site.test":
        raise AssertionError(host)
    Path(marker).write_text(str(os.getpid()))
    if outcome in ("deadline", "stop"):
        threading.Event().wait(15)
        Path(marker).with_suffix(".returned").touch()
    if outcome == "failure":
        raise socket.gaierror(socket.EAI_NONAME, "fixture name not found")
    return native("127.0.0.1", *args, **kwargs)

socket.getaddrinfo = getaddrinfo
runpy.run_path(sys.argv[0], run_name="__main__")
"""


@pytest.mark.slow
@pytest.mark.parametrize(
    ("outcome", "state", "reason", "version", "requests"),
    [
        ("deadline", "completed", None, None, ["/robots.txt", "/"]),
        ("stop", "stopped", "requested", None, ["/robots.txt"]),
        ("success", "completed", None, "http_2", ["/robots.txt", "/"]),
        ("failure", "completed", None, None, ["/robots.txt", "/"]),
    ],
    ids=("deadline", "stop", "success", "failure"),
)
def test_crawl_joins_default_probe_dns_before_its_passes(
    outcome: str,
    state: str,
    reason: str | None,
    version: str | None,
    requests: list[str],
    temp_workspace: TempWorkspace,
    fixture_tls_hosts: StartTlsHosts,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hosts = fixture_tls_hosts(
        Site({"/": Page(body="<p>Seed</p>")}), Site({}), alpn=("h2", "http/1.1")
    )
    port = urlsplit(hosts.secure_site.base_url).port
    in_dns = tmp_path / "probe-dns-pid"
    stop = StopSignal()
    joined: list[bool] = []
    parent_lookups: list[str] = []
    native_dns, native_spawn = socket.getaddrinfo, asyncio.create_subprocess_exec

    def parent_dns(host: str, *args: Any, **kwargs: Any) -> Any:
        if host == "site.test":
            parent_lookups.append(host)
            # On the old path the second lookup is the probe in Runner's default executor.
            if len(parent_lookups) > 1:
                in_dns.write_text(str(os.getpid()))
                if outcome in {"deadline", "stop"}:
                    threading.Event().wait(4)
                if outcome == "failure":
                    raise socket.gaierror(socket.EAI_NONAME, "fixture name not found")
            host = "127.0.0.1"
        return native_dns(host, *args, **kwargs)

    async def spawn(executable: str, *args: str, **kwargs: Any) -> asyncio.subprocess.Process:
        if args[:2] == ("-I", "-S") and Path(args[2]).name == "_dns_worker.py":
            args = (*args[:2], "-c", _WORKER_DNS, str(in_dns), outcome, *args[2:])
        return await native_spawn(executable, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", parent_dns)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def check_joined(_context: PassContext) -> None:
        pid = int(in_dns.read_text())
        joined.append(not psutil.pid_exists(pid))

    async def request_stop() -> None:
        # The marker is shared with a child interpreter that has no event on this loop.
        while not in_dns.exists() or not in_dns.read_text():  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        stop.set("requested")

    @asynccontextmanager
    async def fetchers(policy: FetchPolicy, clock: Clock) -> AsyncIterator[Fetcher]:
        watcher = asyncio.create_task(request_stop()) if outcome == "stop" else None
        try:
            async with aiohttp_fetcher(policy, clock, trust_anchors=hosts.trust_anchors) as fetcher:
                yield fetcher
        finally:
            if watcher is not None:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher

    result = crawl_result(
        f"https://site.test:{port}/",
        Hooks(passes=(Pass("check_dns_joined", check_joined),)),
        fetchers=fetchers,
        stop=stop,
        concurrency=1,
        retries=0,
        network_wait=0,
        timeout=2,
    )

    assert (result.summary.state, result.summary.stop_reason) == (state, reason)
    assert [request.path for request in hosts.secure_site.requests] == requests
    assert query(result.crawl_file, "SELECT http_version FROM origins") == [(version,)]
    assert joined == [True]
    assert not in_dns.with_suffix(".returned").exists()
    assert parent_lookups == ["site.test"]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("address", "family"), [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)]
)
async def test_system_resolver_returns_native_addresses(
    address: str, family: socket.AddressFamily
) -> None:
    if family == socket.AF_INET6:
        try:
            socket.getaddrinfo(address, 443, type=socket.SOCK_STREAM, flags=socket.AI_ADDRCONFIG)
        except socket.gaierror:
            pytest.skip("This system resolver excludes IPv6 under AI_ADDRCONFIG")

    assert [
        (answer["host"], answer["port"], answer["family"])
        for answer in await resolve_system(address, 443)
    ] == [(address, 443, family)]


@pytest.mark.slow
async def test_cancelling_during_dns_spawn_still_joins_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned: asyncio.Future[asyncio.subprocess.Process] = asyncio.get_running_loop().create_future()
    hand_over_child = asyncio.Event()
    native_spawn = asyncio.create_subprocess_exec

    async def start_then_hold(
        executable: str, *args: str, **kwargs: Any
    ) -> asyncio.subprocess.Process:
        child = await native_spawn(
            executable, *args[:2], "-c", "import threading; threading.Event().wait(15)", **kwargs
        )
        spawned.set_result(child)
        await hand_over_child.wait()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start_then_hold)
    lookup = asyncio.create_task(resolve_system("site.test", 443))
    try:
        child = await spawned
        lookup.cancel()
        await asyncio.sleep(0)
        lookup.cancel()
        await asyncio.sleep(0)
        hand_over_child.set()
        with pytest.raises(asyncio.CancelledError):
            async with asyncio.timeout(3):
                await asyncio.shield(lookup)
        assert child.returncode is not None
        assert not psutil.pid_exists(child.pid)
    finally:
        hand_over_child.set()
        if spawned.done() and not spawned.cancelled():
            child = spawned.result()
            with suppress(ProcessLookupError):
                if child.returncode is None:
                    child.kill()
            await child.wait()
        await asyncio.gather(lookup, return_exceptions=True)
