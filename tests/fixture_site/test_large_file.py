"""`LargeFile` routes (design D9 of 000-scaffold-project)."""

import hashlib

import aiohttp

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import LargeFile, Site

# sha256 of bytes 0..255 repeated, cut at 3,000,000 bytes; computed once outside the server.
SHA256_OF_3_000_000_BYTES = "1913233a0a87fe912497ee543021c40adc5d414614fc76fdff3e0c08b6a1d981"


async def test_a_large_file_streams_its_documented_pattern(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/big.bin": LargeFile(size=3_000_000)}))
    timeout = aiohttp.ClientTimeout(total=60)

    async with (
        aiohttp.ClientSession(timeout=timeout) as session,
        session.get(server.url("/big.bin")) as response,
    ):
        body = await response.read()
        length = response.headers["Content-Length"]

    assert (length, len(body), hashlib.sha256(body).hexdigest()) == (
        "3000000",
        3_000_000,
        SHA256_OF_3_000_000_BYTES,
    )
