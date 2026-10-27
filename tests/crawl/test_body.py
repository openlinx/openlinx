"""Reading a response body up to its cap (022-add-fetch-policy D1; Pure)."""

import asyncio
import gzip
import tracemalloc
import zlib
from collections.abc import AsyncIterator

import brotli
import pytest

from spider.crawl.fetch.body import BODY_LIMIT, Body, BodyDecodingError, read_body

# A product listing, as a shop's category page repeats it.
ROW = b'<li class="product"><a href="/p/1">Trail shoe</a> <span>89.00</span></li>\n'


async def _chunks(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _read(data: bytes, limit: int, chunk_size: int = 4096) -> tuple[int, bool, bool]:
    body = asyncio.run(read_body(_chunks(data, chunk_size), None, limit))
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


def _packed(data: bytes, coding: str) -> bytes:
    if coding == "gzip":
        return gzip.compress(data, mtime=0)
    if coding == "br":
        packed: bytes = brotli.compress(data)
        return packed
    if coding == "deflate":
        return zlib.compress(data)
    # Raw deflate, without the zlib wrapper, as some servers send for "deflate".
    packer = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return packer.compress(data) + packer.flush()


def _decoded(packed: bytes, coding: str, limit: int = BODY_LIMIT) -> Body:
    return asyncio.run(read_body(_chunks(packed, 4096), coding, limit))


@pytest.mark.parametrize("coding", ["gzip", "br", "deflate", "raw deflate"])
def test_a_compressed_body_is_decoded(coding: str) -> None:
    page = ROW * 1000
    packed = _packed(page, coding)

    body = _decoded(packed, "deflate" if coding == "raw deflate" else coding)

    assert (body.data == page, body.truncated, body.size_bytes, body.transferred_bytes) == (
        True,
        False,
        len(page),
        len(packed),
    )


@pytest.mark.parametrize("coding", ["gzip", "br"])
def test_a_compressed_body_is_capped_after_decoding(coding: str) -> None:
    # A decompression bomb: 25 MiB of zeros in a body of a few kilobytes.
    packed = _packed(bytes(25 * 1024 * 1024), coding)

    body = _decoded(packed, coding)

    assert (len(body.data), body.truncated, body.size_bytes) == (BODY_LIMIT, True, None)


@pytest.mark.parametrize("coding", ["gzip", "br"])
def test_a_bomb_in_one_chunk_is_decoded_only_up_to_the_cap(coding: str) -> None:
    # 64 MiB of zeros, packed into one chunk as small as a connection reads at once.
    packed = _packed(bytes(64 * 1024 * 1024), coding)
    limit = 1024 * 1024

    tracemalloc.start()
    try:
        body = asyncio.run(read_body(_chunks(packed, len(packed)), coding, limit))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert (len(body.data), body.truncated, peak < 8 * limit) == (limit, True, True)


def test_stacked_codings_are_decoded_last_first() -> None:
    page = ROW * 1000
    packed = brotli.compress(gzip.compress(page, mtime=0))

    body = _decoded(packed, "gzip, br")

    assert (body.data == page, body.size_bytes) == (True, len(page))


@pytest.mark.parametrize(
    ("packed", "coding"),
    [
        (ROW * 10, "gzip"),
        (ROW * 10, "br"),
        (gzip.compress(ROW * 1000, mtime=0)[:-100], "gzip"),
    ],
    ids=["not gzip", "not br", "gzip cut short"],
)
def test_a_body_that_fails_to_decode_is_refused(packed: bytes, coding: str) -> None:
    with pytest.raises(BodyDecodingError):
        _decoded(packed, coding)


def test_a_coding_that_was_not_offered_is_kept_as_received() -> None:
    packed = ROW * 10

    body = _decoded(packed, "zstd")

    assert (body.data, body.size_bytes, body.transferred_bytes) == (packed, None, len(packed))


def test_an_empty_body_under_a_coding_is_empty() -> None:
    # A redirect with no body, from a server that labels every response gzip.
    body = _decoded(b"", "gzip")

    assert (body.data, body.size_bytes, body.transferred_bytes) == (b"", 0, 0)
