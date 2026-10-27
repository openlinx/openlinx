"""Reading a response body up to its cap (022-add-fetch-policy D1; Pure)."""

import asyncio
from collections.abc import AsyncIterator

from spider.crawl.fetch.body import read_body

# A product listing, as a shop's category page repeats it.
ROW = b'<li class="product"><a href="/p/1">Trail shoe</a> <span>89.00</span></li>\n'


async def _chunks(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _read(data: bytes, limit: int, chunk_size: int = 4096) -> tuple[int, bool, bool]:
    body = asyncio.run(read_body(_chunks(data, chunk_size), limit))
    return len(body.data), body.truncated, data.startswith(body.data)


def test_a_body_at_the_cap_is_read_whole() -> None:
    page = ROW * 1000

    assert _read(page, limit=len(page)) == (len(page), False, True)


def test_a_body_past_the_cap_is_cut_at_the_cap() -> None:
    page = ROW * 1000

    assert _read(page + b"<p>", limit=len(page)) == (len(page), True, True)


def test_the_cap_falls_inside_a_chunk() -> None:
    page = ROW * 1000

    assert _read(page, limit=10_000, chunk_size=65_536) == (10_000, True, True)
