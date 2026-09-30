"""Pages served from files (design D9 of 000-scaffold-project)."""

import subprocess
import sys
from pathlib import Path

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
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


async def fetch_body(server: ServerHandle, path: str) -> bytes:
    async with aiohttp.ClientSession() as session, session.get(server.url(path)) as response:
        return await response.read()


async def test_a_template_page_gets_the_server_base_url(fixture_site: StartSite) -> None:
    page = Page(body='<a href="{{base_url}}/about">', template=True)
    server = fixture_site(Site(routes={"/": page}))

    assert await fetch_body(server, "/") == f'<a href="{server.base_url}/about">'.encode()


async def test_a_page_without_template_is_served_unchanged(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="{{base_url}}/about">')}))

    assert await fetch_body(server, "/") == b'<a href="{{base_url}}/about">'


# ProxyHandler({}): on Windows, urllib falls back to the registry's proxy settings.
FETCH_IN_A_CHILD = (
    "import sys, urllib.request\n"
    "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
    "sys.stdout.buffer.write(opener.open(sys.argv[1], timeout=30).read())\n"
)


def test_a_child_process_can_fetch_a_page(fixture_site: StartSite) -> None:
    server = fixture_site(basic.SITE)

    fetched = subprocess.run(
        [sys.executable, "-c", FETCH_IN_A_CHILD, server.url("/")],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout

    assert fetched == Path(basic.__file__).with_name("index.html").read_bytes()
