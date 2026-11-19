"""Verify fixture-site request logging."""

import asyncio

import aiohttp
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site, Status
from tests.fixture_site.server import RunningServer


async def test_the_request_log_lists_requests_in_the_order_they_came(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="home"), "/about": Page(body="about")}))

    async with aiohttp.ClientSession() as session:
        async with session.get(server.url("/"), headers={"User-Agent": "probe/1.0"}) as home:
            await home.read()
        async with session.head(server.url("/about")):
            pass

    log = server.requests
    assert ([(entry.method, entry.path) for entry in log], log[0].headers["User-Agent"]) == (
        [("GET", "/"), ("HEAD", "/about")],
        "probe/1.0",
    )


async def test_the_request_log_counts_the_most_simultaneous_requests(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(
        Site(routes={"/slow": Page(body="slow", delay=0.3), "/fast": Page(body="fast")})
    )

    async with aiohttp.ClientSession() as session:

        async def get(path: str) -> None:
            async with session.get(server.url(path)) as response:
                await response.read()

        await asyncio.gather(get("/slow"), get("/slow"), get("/slow"))
        await get("/fast")

    assert server.most_simultaneous == 3


async def test_computed_site_can_serve_distinct_paths_without_a_request_log() -> None:
    server = RunningServer(Site(resolve=lambda path: Page(body=path)), keep_log=False)
    try:
        async with aiohttp.ClientSession() as session:
            for number in range(32):
                path = f"/page/{number}"
                async with session.get(server.handle.url(path)) as response:
                    assert (response.status, await response.text()) == (200, path)
        assert server.handle.requests == ()
        assert server.handle.most_simultaneous == 1
    finally:
        server.stop()


async def test_declared_dependencies_still_order_requests_without_a_log() -> None:
    site = Site(
        routes={
            "/left": Responses((Status(503, after="/right"), Status(201, after="/earlier"))),
            "/right": Status(202, after="/left"),
        }
    )
    server = RunningServer(site, keep_log=False)
    try:
        async with aiohttp.ClientSession() as session:

            async def status(path: str) -> int:
                async with session.get(server.handle.url(path)) as response:
                    return response.status

            assert await status("/earlier?first") == 404
            # Neither handler can finish before the other request arrives.
            right, left = await asyncio.gather(status("/right"), status("/left"))
            assert (right, left) == (202, 503)
            assert await status("/left") == 201
        assert server.handle.most_simultaneous == 2
        assert server.handle.requests == ()
    finally:
        server.stop()


@pytest.mark.parametrize("keep_log", [True, False])
async def test_a_resolved_dependency_can_follow_an_earlier_unresolved_request(
    keep_log: bool,
) -> None:
    site = Site(
        resolve=lambda path: Page(body="ready", after="/signal") if path == "/wait" else None
    )
    server = RunningServer(site, keep_log=keep_log, after_paths=() if keep_log else ("/signal",))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(server.handle.url("/signal?first")) as signal:
                assert signal.status == 404
            async with session.get(server.handle.url("/wait")) as waited:
                assert (waited.status, await waited.text()) == (200, "ready")
    finally:
        server.stop()


async def test_an_undeclared_resolved_dependency_fails_the_no_log_fixture() -> None:
    site = Site(routes={"/signal": Status(204)}, resolve=lambda path: Status(200, after="/signal"))
    server = RunningServer(site, keep_log=False)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(server.handle.url("/signal")) as signal:
                assert signal.status == 204
            async with session.get(server.handle.url("/wait")) as response:
                status = response.status
    finally:
        with pytest.raises(AssertionError, match=r"/wait.*after_paths.*?/signal"):
            server.stop()
    assert status == 500
