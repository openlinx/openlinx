"""Bodies given as bytes, broken on purpose (design D6 of 026-add-parse-pool)."""

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Bytes, Site

BROKEN = b"<p>caf\xe9 \xff\xfe\x00</p"


async def test_a_bytes_route_answers_with_its_exact_bytes_and_content_type(
    fixture_site: StartSite,
) -> None:
    route = Bytes(BROKEN, content_type="text/html; charset=utf-8")
    server = fixture_site(Site(routes={"/broken": route}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/broken")) as response:
        body = await response.read()

    assert (response.status, response.headers["Content-Type"], body) == (
        200,
        "text/html; charset=utf-8",
        BROKEN,
    )


async def test_a_bytes_route_without_a_content_type_is_octet_stream(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(Site(routes={"/blob": Bytes(b"\x89PNG")}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/blob")) as response:
        await response.read()

    assert response.headers["Content-Type"] == "application/octet-stream"
