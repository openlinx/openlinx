"""`Robots`, `Sitemap` and `SitemapIndex` routes (design D9 of 000-scaffold-project)."""

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Robots, Site
from tests.fixture_site.server import ServerHandle


async def fetch(server: ServerHandle, path: str) -> tuple[int, str, bytes]:
    async with aiohttp.ClientSession() as session, session.get(server.url(path)) as response:
        return response.status, response.headers["Content-Type"], await response.read()


async def test_robots_txt_is_served_as_declared(fixture_site: StartSite) -> None:
    text = "User-agent: *\nDisallow: /private/\n"
    server = fixture_site(Site(routes={"/robots.txt": Robots(text)}))

    assert await fetch(server, "/robots.txt") == (
        200,
        "text/plain; charset=utf-8",
        b"User-agent: *\nDisallow: /private/\n",
    )
