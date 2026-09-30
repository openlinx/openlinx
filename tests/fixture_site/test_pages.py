"""Pages served from files (design D9 of 000-scaffold-project)."""

from pathlib import Path

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.sites.basic import site as basic
from tests.fixture_site.sites.exact import site as exact


async def test_a_page_is_served_from_its_file(fixture_site: StartSite) -> None:
    server = fixture_site(basic.SITE)

    async with aiohttp.ClientSession() as session, session.get(server.url("/")) as response:
        body = await response.read()

    assert (response.status, response.headers["Content-Type"], body) == (
        200,
        "text/html; charset=utf-8",
        Path(basic.__file__).with_name("index.html").read_bytes(),
    )


async def test_a_file_is_served_byte_for_byte(fixture_site: StartSite) -> None:
    server = fixture_site(exact.SITE)

    async with aiohttp.ClientSession() as session, session.get(server.url("/mixed")) as response:
        body = await response.read()

    assert body == b"a\r\nb\nc"
