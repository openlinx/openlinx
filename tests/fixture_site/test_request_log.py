"""The request log (design D9 of 000-scaffold-project)."""

import asyncio

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site


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
