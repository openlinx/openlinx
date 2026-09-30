"""Options every route takes: headers, content_type, delay, hang (design D9 of 000)."""

import time
from pathlib import Path

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
    page = Page(file="cp1251.html", content_type="text/html; charset=windows-1251")
    server = fixture_site(Site(root=Path(exact.__file__).parent, routes={"/": page}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/")) as response:
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
