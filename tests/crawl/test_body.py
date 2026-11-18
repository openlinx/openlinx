"""Verify bounded response-body reading and decompression through pure logic."""

import asyncio
import gzip
import hashlib
import tracemalloc
import zlib
from collections.abc import AsyncIterator

import brotlicffi
import pytest

from openlinx.crawl.fetch.body import BODY_LIMIT, Body, BodyDecodingError, read_body

# A product listing, as a shop's category page repeats it.
ROW = b'<li class="product"><a href="/p/1">Trail shoe</a> <span>89.00</span></li>\n'


async def _chunks(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _read(data: bytes, limit: int, chunk_size: int = 4096) -> tuple[int, bool, bool, int]:
    body = asyncio.run(read_body(_chunks(data, chunk_size), None, limit))
    return len(body.data), body.truncated, data.startswith(body.data), body.transferred_bytes


def test_a_body_at_the_cap_is_read_whole() -> None:
    page = ROW * 1000

    assert _read(page, limit=len(page)) == (len(page), False, True, len(page))


def test_a_body_past_the_cap_is_cut_at_the_cap() -> None:
    page = ROW * 1000

    # The last chunk was read whole: the bytes read, not the bytes kept.
    assert _read(page + b"<p>", limit=len(page)) == (len(page), True, True, len(page) + 3)


def test_the_cap_falls_inside_a_chunk() -> None:
    page = ROW * 1000

    assert _read(page, limit=10_000, chunk_size=65_536) == (10_000, True, True, 65_536)


def _packed(data: bytes, coding: str) -> bytes:
    if coding == "gzip":
        return gzip.compress(data, mtime=0)
    if coding == "br":
        packed: bytes = brotlicffi.compress(data)
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

    assert (body.data == page, body.truncated, body.transferred_bytes) == (
        True,
        False,
        len(packed),
    )


@pytest.mark.parametrize("coding", ["gzip", "br"])
def test_a_compressed_body_is_capped_after_decoding(coding: str) -> None:
    # A decompression bomb: 25 MiB of zeros in a body of a few kilobytes.
    packed = _packed(bytes(25 * 1024 * 1024), coding)

    body = _decoded(packed, coding)

    assert (len(body.data), body.truncated) == (BODY_LIMIT, True)


@pytest.mark.parametrize(
    ("padding", "truncated", "transferred"),
    [(39, False, 64), (40, True, 65)],
    ids=["exact", "one-over"],
)
def test_a_compressed_body_is_capped_as_transferred(
    padding: int, truncated: bool, transferred: int
) -> None:
    # A complete 25-byte gzip member followed by zero padding isolates the wire cap.
    packed = gzip.compress(b"hello", mtime=0) + b"\0" * padding

    body = _decoded(packed, "gzip", limit=64)

    assert (body.data, body.truncated, body.transferred_bytes) == (b"hello", truncated, transferred)


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


@pytest.mark.parametrize("coding", ["br", "br, gzip", "gzip, br"])
async def test_brotli_allocates_output_within_a_small_remaining_budget(coding: str) -> None:
    page = ROW * 1000
    if coding == "gzip, br":
        expected = b"hello"
        # The gzip member ends within the cap, but the intermediate still exceeds it.
        packed = _packed(gzip.compress(expected, mtime=0) + page, "br")
    else:
        expected = page[:512]
        packed = _packed(page, "br")
        if coding == "br, gzip":
            packed = gzip.compress(packed, mtime=0)

    tracemalloc.start()
    try:
        body = await read_body(_pieces(packed), coding, limit=512)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert (body.data, body.truncated) == (expected, True)
    assert peak < 16 * 1024


def test_stacked_codings_are_decoded_last_first() -> None:
    page = ROW * 1000
    packed = brotlicffi.compress(gzip.compress(page, mtime=0))

    body = _decoded(packed, "gzip, br")

    assert body.data == page


def test_a_stacked_zstd_body_cannot_exceed_the_intermediate_cap() -> None:
    # One zstd frame in two reads: a raw block holding a 25-byte gzip member for
    # "hello", followed by an RLE block holding 100 bytes of zero padding.
    first = bytes.fromhex("28b52ffd207dc800001f8b08000000000002ffcb48cdc9c9070086a6103605000000")
    last = bytes.fromhex("23030000")

    body = asyncio.run(read_body(_pieces(first, last), "gzip, zstd", limit=55))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"hello", True, 38)


def test_a_zstd_decoder_refuses_a_window_above_the_http_limit() -> None:
    # A 16 MiB window enclosing a five-byte raw block, without a content-size field.
    packed = bytes.fromhex("28b52ffd007029000068656c6c6f")

    with pytest.raises(BodyDecodingError):
        _decoded(packed, "zstd")


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


def test_an_unsupported_coding_is_kept_as_received() -> None:
    packed = ROW * 10

    body = _decoded(packed, "x-unknown")

    assert (body.data, body.transferred_bytes) == (packed, len(packed))


def test_an_empty_body_under_a_coding_is_empty() -> None:
    # A redirect with no body, from a server that labels every response gzip.
    body = _decoded(b"", "gzip")

    assert (body.data, body.transferred_bytes) == (b"", 0)


def test_stacked_codings_decode_a_body_up_to_the_cap() -> None:
    # A server that gzips a file that is gzipped already, sending it a few bytes to a read: near
    # the cap, the outer layer holds trailer bytes that give no output of their own.
    photo = b"".join(hashlib.sha256(n.to_bytes(4)).digest() for n in range(2000))
    page = ROW * 50 + photo
    packed = gzip.compress(gzip.compress(page, mtime=0), mtime=0)

    body = asyncio.run(read_body(_chunks(packed, 7), "gzip, gzip", len(page)))

    assert (body.data == page, body.truncated) == (True, False)


def test_a_zlib_body_whose_first_chunk_is_one_byte_is_decoded() -> None:
    # A server that trickles its body, one byte to a read.
    page = ROW * 100
    packed = zlib.compress(page)

    body = asyncio.run(read_body(_chunks(packed, 1), "deflate", BODY_LIMIT))

    assert body.data == page


def test_every_member_of_a_gzip_body_is_decoded() -> None:
    # Two gzip files concatenated, as a server that appends a compressed footer sends them.
    head, tail = ROW * 500, b"<footer>Shop</footer>\n"
    packed = gzip.compress(head, mtime=0) + gzip.compress(tail, mtime=0)

    body = _decoded(packed, "gzip")

    assert body.data == head + tail


async def _pieces(*pieces: bytes) -> AsyncIterator[bytes]:
    for piece in pieces:
        yield piece


_ZSTD_HELLO = bytes.fromhex("28b52ffd200529000068656c6c6f")
_ZSTD_SKIPPABLE = bytes.fromhex("5f2a4d180400000028b52ffd")


@pytest.mark.parametrize("split", range(29))
def test_concatenated_zstd_frames_are_decoded_across_input_boundaries(split: int) -> None:
    packed = _ZSTD_HELLO * 2

    body = asyncio.run(read_body(_pieces(packed[:split], packed[split:]), "zstd"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"hellohello", False, 28)


@pytest.mark.parametrize("chunk_size", [1, 64])
def test_zstd_skippable_frames_leave_only_the_decoded_body(chunk_size: int) -> None:
    # The skippable payload itself looks like zstd magic and must be ignored.
    packed = _ZSTD_SKIPPABLE + _ZSTD_HELLO + _ZSTD_SKIPPABLE + _ZSTD_HELLO + _ZSTD_SKIPPABLE

    body = asyncio.run(read_body(_chunks(packed, chunk_size), "zstd"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"hellohello", False, 64)


def test_many_zstd_skippable_frames_can_form_an_empty_body() -> None:
    packed = _ZSTD_SKIPPABLE * 257

    body = asyncio.run(read_body(_pieces(packed), "zstd"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"", False, 3084)


@pytest.mark.parametrize(
    ("limit", "tail", "truncated"),
    [(65_542, b"hello", False), (65_539, b"he", True)],
    ids=["exact-budget", "budget-inside-next-frame"],
)
def test_zstd_drains_buffered_output_before_advancing_to_the_next_frame(
    limit: int, tail: bytes, truncated: bool
) -> None:
    # A 13-byte frame with an RLE block of 65,537 copies of "x".
    packed = bytes.fromhex("28b52ffda0010001000b000878") + _ZSTD_HELLO

    body = asyncio.run(read_body(_pieces(packed), "zstd", limit))

    assert (body.data, body.truncated, body.transferred_bytes) == (
        b"x" * 65_537 + tail,
        truncated,
        27,
    )


@pytest.mark.parametrize("coding", ["gzip", "deflate", "br"])
def test_bytes_after_a_finished_stream_are_ignored(coding: str) -> None:
    # A server that ends every response with a line break after the compressed body.
    page = ROW * 100

    body = asyncio.run(read_body(_pieces(_packed(page, coding), b"\r\n"), coding, BODY_LIMIT))

    assert body.data == page


def test_a_gzip_member_boundary_split_after_its_first_byte_is_decoded() -> None:
    head, tail = ROW * 500, b"<footer>Shop</footer>\n"
    first = gzip.compress(head, mtime=0)
    packed = first + gzip.compress(tail, mtime=0)
    # The read ends right after the next member's first byte, 0x1f.
    split = len(first) + 1

    body = asyncio.run(read_body(_pieces(packed[:split], packed[split:]), "gzip", BODY_LIMIT))

    assert body.data == head + tail


@pytest.mark.parametrize(
    "chunking", ["together", "members", "separate prefix", "attached prefix", "one byte"]
)
def test_gzip_members_are_decoded_across_chunk_boundaries(chunking: str) -> None:
    first = gzip.compress(b"first", mtime=0)
    second = gzip.compress(b"second", mtime=0)
    pieces = {
        "together": [first + second],
        "members": [first, second],
        "separate prefix": [first, second[:1], second[1:]],
        "attached prefix": [first + second[:1], second[1:]],
        "one byte": [bytes([byte]) for byte in first + second],
    }[chunking]

    body = asyncio.run(read_body(_pieces(*pieces), "gzip"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"firstsecond", False, 51)


def test_a_gzip_member_after_a_separate_prefix_is_bounded() -> None:
    first = gzip.compress(b"first", mtime=0)
    second = gzip.compress(b"x" * 1024, mtime=0)

    body = asyncio.run(read_body(_pieces(first, second[:1], second[1:]), "gzip", 128))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"first" + b"x" * 123, True, 54)


@pytest.mark.parametrize("junk", [b"X", b"\x00", b"\n"])
@pytest.mark.parametrize("chunking", ["together", "separate prefix", "one byte", "before member"])
def test_trailing_junk_cannot_restart_a_gzip_member(junk: bytes, chunking: str) -> None:
    first = gzip.compress(b"first", mtime=0)
    second = gzip.compress(b"second", mtime=0)
    packed = first + second[:1] + junk + second[1:]
    pieces = {
        "together": [packed],
        "separate prefix": [first, second[:1], junk, second[1:]],
        "one byte": [bytes([byte]) for byte in packed],
        "before member": [first, junk, second],
    }[chunking]

    body = asyncio.run(read_body(_pieces(*pieces), "gzip"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"first", False, 52)
