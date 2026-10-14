"""Routes computed per request, for sites too large to declare (design D6 of 026-add-parse-pool)."""

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site


def made_for(path: str) -> Route | None:
    return Page(body=f"made for {path}") if path.startswith("/p/") else None


async def test_a_path_that_no_route_declares_is_resolved_by_the_site(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(Site(routes={"/p/1": Page(body="declared")}, resolve=made_for))

    answers = []
    async with aiohttp.ClientSession() as session:
        for path in ("/p/1", "/p/7", "/q"):
            async with session.get(server.url(path)) as response:
                answers.append((response.status, await response.text()))

    assert answers == [(200, "declared"), (200, "made for /p/7"), (404, "404: Not Found")]
