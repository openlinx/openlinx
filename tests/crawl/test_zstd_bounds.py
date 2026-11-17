"""Verify zstd output and intermediate caps through the body reader and the Crawl."""

import asyncio
import gzip
import tracemalloc
from collections.abc import AsyncIterator
from pathlib import Path

import brotli
import pytest

from openlinx.crawl.fetch.body import Body, read_body
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

_GZIP_HELLO = bytes.fromhex("1f8b08000000000002ffcb48cdc9c9070086a6103605000000")


def _zstd_run(size: int, *, byte: bytes, prefix: bytes = b"") -> bytes:
    # A frame with a 128 KiB window and no content-size field, followed by an optional
    # raw block and RLE blocks. Each RLE block encodes up to 128 KiB in four bytes.
    frame = bytes.fromhex("28b52ffd0038")
    if prefix:
        frame += (len(prefix) << 3).to_bytes(3, "little") + prefix
    full, tail = divmod(size - len(prefix) - 1, 131_072)
    full_block = bytes.fromhex("020010") + byte
    last_block = (((tail + 1) << 3) | 3).to_bytes(3, "little") + byte
    return frame + full_block * full + last_block


async def _pieces(*pieces: bytes) -> AsyncIterator[bytes]:
    for piece in pieces:
        yield piece


async def _measured_body(chunks: AsyncIterator[bytes], coding: str) -> tuple[Body, int]:
    tracemalloc.start()
    try:
        body = await read_body(chunks, coding, limit=196_608)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return body, peak


@pytest.mark.parametrize(
    ("size", "truncated", "transferred"),
    [(20_971_520, False, 655), (20_971_521, True, 655), (26_214_400, True, 815)],
    ids=["exact", "one-over", "25-MiB"],
)
def test_zstd_reads_at_most_the_decoded_body_cap(
    size: int, truncated: bool, transferred: int
) -> None:
    packed = _zstd_run(size, byte=b" ", prefix=b"<html>")

    body = asyncio.run(read_body(_pieces(packed), "zstd"))

    assert (len(body.data), body.truncated, body.transferred_bytes) == (
        20_971_520,
        truncated,
        transferred,
    )
    assert body.data.startswith(b"<html>")
    assert body.data.count(b" ", 6) == 20_971_514


def test_zstd_stops_decoding_inside_a_chunk() -> None:
    packed = _zstd_run(26_214_400, byte=b"x")

    async def chunks() -> AsyncIterator[bytes]:
        # The first read decodes to 128 KiB. The 192 KiB cap falls within the next read.
        yield packed[:10]
        yield packed[10:]
        pytest.fail("The body reader pulled another chunk past the decoded cap")

    body, peak = asyncio.run(_measured_body(chunks(), "zstd"))

    assert (body.data, body.truncated, body.transferred_bytes) == (b"x" * 196_608, True, 806)
    # Allow copies of the retained bytes while catching a full 25 MiB inflation.
    assert peak < 1_572_864


@pytest.mark.parametrize(
    ("size", "truncated"), [(196_608, False), (196_609, True)], ids=["exact", "one-over"]
)
def test_stacked_codings_apply_the_decoded_body_cap(size: int, truncated: bool) -> None:
    zstd = _zstd_run(size, byte=b"x")
    packed = brotli.compress(gzip.compress(zstd, mtime=0))

    body = asyncio.run(read_body(_pieces(packed), "zstd, gzip, br", limit=196_608))

    assert (body.data, body.truncated) == (b"x" * 196_608, truncated)


@pytest.mark.parametrize(
    ("size", "truncated"),
    [(196_608, False), (196_609, True), (26_214_400, True)],
    ids=["exact", "one-over", "25-MiB"],
)
def test_stacked_codings_apply_a_cumulative_intermediate_cap(size: int, truncated: bool) -> None:
    # The middle stage yields a complete gzip member plus zero padding. The final output
    # stays at five bytes, even when the middle stage hits its own cap.
    zstd = _zstd_run(size, byte=b"\0", prefix=_GZIP_HELLO)
    encoder = brotli.Compressor()
    # Flush after the member and the first 128 KiB RLE block to spend budget on both reads.
    first = encoder.process(zstd[:38]) + encoder.flush()
    last = encoder.process(zstd[38:]) + encoder.finish()

    body, peak = asyncio.run(_measured_body(_pieces(first, last), "gzip, zstd, br"))

    assert (body.data, body.truncated) == (b"hello", truncated)
    assert peak < 1_572_864


def test_a_zstd_bomb_stops_at_the_decoded_cap(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    (tmp_path / "huge.html.zst").write_bytes(_zstd_run(26_214_400, byte=b" ", prefix=b"<html>"))
    server = fixture_site(
        Site(
            root=tmp_path,
            routes={
                "/": Page(body='<a href="/huge.html">Huge</a>'),
                "/huge.html": Page(
                    file="huge.html.zst",
                    content_type="text/html",
                    headers=[("Content-Encoding", "zstd")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, body_truncated, parsed, parse_error, size_bytes, transferred_bytes,"
        " content_encoding FROM urls WHERE url = ?",
        [server.url("/huge.html")],
    ) == [("fetched", 1, 0, "body_too_large", None, 815, "zstd")]
