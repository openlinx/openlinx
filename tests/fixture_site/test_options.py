"""Options every route takes: headers, content_type, delay, hang (design D9 of 000)."""

from pathlib import Path

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
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
