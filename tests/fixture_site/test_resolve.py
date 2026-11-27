"""Verify computed fixture routes through real HTTP requests."""

import aiohttp
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site


def _made_for(path: str) -> Route | None:
    assert path != "/p/1", "the resolver must not run for an explicitly declared path"
    return Page(body=f"made for {path}") if path.startswith("/p/") else None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param("/p/1", (200, "declared"), id="declared-wins"),
        pytest.param("/p/7", (200, "made for /p/7"), id="resolved"),
        pytest.param("/q", (404, None), id="unresolved"),
    ],
)
async def test_fixture_site_uses_a_resolver_for_undeclared_paths(
    fixture_site: StartSite, path: str, expected: tuple[int, str | None]
) -> None:
    server = fixture_site(Site(routes={"/p/1": Page(body="declared")}, resolve=_made_for))

    async with aiohttp.ClientSession() as session, session.get(server.url(path)) as response:
        body = await response.text() if expected[1] is not None else None
        assert (response.status, body) == expected
