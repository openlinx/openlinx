"""`Redirect` routes and redirect chains (design D9 of 000-scaffold-project)."""

import aiohttp
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site, redirect_chain


async def test_a_redirect_answers_with_its_status_and_location_as_declared(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(Site(routes={"/a": Redirect("/b", status=301), "/b": Page(body="b")}))

    async with (
        aiohttp.ClientSession() as session,
        session.get(server.url("/a"), allow_redirects=False) as response,
    ):
        location = response.headers["Location"]

    assert (response.status, location) == (301, "/b")


async def test_a_redirect_chain_takes_exactly_its_hops(fixture_site: StartSite) -> None:
    routes = {**redirect_chain("/r", hops=3, to="/final"), "/final": Page(body="final")}
    server = fixture_site(Site(routes=routes))

    async with aiohttp.ClientSession() as session, session.get(server.url("/r1")) as response:
        await response.read()

    assert ([str(hop.url.path) for hop in response.history], response.status) == (
        ["/r1", "/r2", "/r3"],
        200,
    )


async def test_a_redirect_loop_exhausts_the_client(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(routes={"/loop-a": Redirect("/loop-b"), "/loop-b": Redirect("/loop-a")})
    )

    async with aiohttp.ClientSession() as session:
        with pytest.raises(aiohttp.TooManyRedirects):
            await session.get(server.url("/loop-a"), max_redirects=10)
