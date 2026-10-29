"""Route options: headers, content_type, delay, hang, reset_after, after (design D9 of 000)."""

import asyncio
import time

import aiohttp
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import RunningServer
from tests.fixture_site.sites.exact import site as exact

CANONICAL_LINK = '<https://example.com/>; rel="canonical"'


async def test_a_route_sends_its_headers_repeated_and_in_order(fixture_site: StartSite) -> None:
    headers = [
        ("Set-Cookie", "a=1"),
        ("Set-Cookie", "b=2"),
        ("X-Robots-Tag", "noindex"),
        ("Link", CANONICAL_LINK),
    ]
    server = fixture_site(Site(routes={"/": Page(body="home", headers=headers)}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/")) as response:
        received = (
            response.headers.getall("Set-Cookie"),
            response.headers["X-Robots-Tag"],
            response.headers["Link"],
        )

    assert received == (["a=1", "b=2"], "noindex", CANONICAL_LINK)


async def test_content_type_overrides_the_extension(fixture_site: StartSite) -> None:
    server = fixture_site(exact.SITE)

    async with aiohttp.ClientSession() as session, session.get(server.url("/cp1251")) as response:
        content_type = response.headers["Content-Type"]

    assert content_type == "text/html; charset=windows-1251"


async def test_delay_holds_back_the_response_headers(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/slow": Page(body="slow", delay=0.5)}))
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        started = time.monotonic()
        async with session.get(server.url("/slow")) as response:
            waited = time.monotonic() - started
            await response.read()

    assert waited >= 0.5


async def test_hang_never_answers_and_the_server_still_stops_quickly() -> None:
    server = RunningServer(Site(routes={"/hang": Page(body="never", hang=True)}))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=0.3)) as session:
            with pytest.raises(TimeoutError):
                await session.get(server.handle.url("/hang"))
    finally:
        started = time.monotonic()
        server.stop()
        stopped_in = time.monotonic() - started

    assert stopped_in < 2


async def test_reset_after_resets_the_connection_inside_the_body(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/reset": Page(body="x" * 100_000, reset_after=100)}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/reset")) as response:
        received = (response.status, response.content_length)
        with pytest.raises(aiohttp.ClientError):
            await response.read()

    assert received == (200, 100_000)


async def test_after_holds_the_response_until_the_site_receives_the_other_path(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(Site(routes={"/a": Page(body="a", after="/b"), "/b": Page(body="b")}))

    async with aiohttp.ClientSession() as session:

        async def body(path: str) -> str:
            async with session.get(server.url(path)) as response:
                return await response.text()

        held = asyncio.create_task(body("/a"))
        done, _ = await asyncio.wait({held}, timeout=0.3)
        answered = (len(done), await body("/b"), await held)

    assert answered == (0, "b", "a")


async def test_after_fails_the_test_when_its_path_is_never_requested() -> None:
    server = RunningServer(Site(routes={"/a": Page(body="a", after="/never")}), after_seconds=0.2)
    try:
        async with aiohttp.ClientSession() as session, session.get(server.handle.url("/a")) as got:
            status = got.status
    finally:
        with pytest.raises(AssertionError, match=r"/a waited 0.2 s for a request for /never"):
            server.stop()

    assert status == 503
