"""`Redirect` routes and redirect chains (design D9 of 000-scaffold-project)."""

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site


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
