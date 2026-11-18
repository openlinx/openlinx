"""Check the HTTP zstd window limit on each frame of a Resource."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from openlinx.crawl.fetch.body import BodyDecodingError, read_body
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# All four frames end with one raw block containing "hello". The window descriptor
# is independent of the optional four-byte content size (RFC 8878 section 3.1.1.1).
WINDOW_8_MIB = bytes.fromhex("28b52ffd 00 68 290000 68656c6c6f")
WINDOW_16_MIB = bytes.fromhex("28b52ffd 00 70 290000 68656c6c6f")
WINDOW_8_MIB_WITH_SIZE = bytes.fromhex("28b52ffd 80 68 05000000 290000 68656c6c6f")
WINDOW_16_MIB_WITH_SIZE = bytes.fromhex("28b52ffd 80 70 05000000 290000 68656c6c6f")
WINDOW_9_MIB_WITH_SIZE = bytes.fromhex("28b52ffd 80 69 05000000 290000 68656c6c6f")


def _fixture_header(frame: bytes) -> tuple[int, int | None]:
    assert frame[:4] == bytes.fromhex("28b52ffd")
    frame_descriptor, window_descriptor = frame[4:6]
    assert frame_descriptor in (0x00, 0x80)
    base = 1 << (10 + (window_descriptor >> 3))
    window_size = base + (base // 8) * (window_descriptor & 7)
    content_size = int.from_bytes(frame[6:10], "little") if frame_descriptor == 0x80 else None
    return window_size, content_size


@pytest.mark.parametrize(
    ("at_limit", "above_limit", "declared_size", "frame_bytes"),
    [
        (WINDOW_8_MIB, WINDOW_16_MIB, None, 14),
        (WINDOW_8_MIB_WITH_SIZE, WINDOW_16_MIB_WITH_SIZE, 5, 18),
    ],
    ids=["content-size-absent", "content-size-five"],
)
@pytest.mark.parametrize(
    ("prefix", "decoded_size", "prefix_bytes"),
    [(b"", 5, 0), (WINDOW_8_MIB, 10, 14)],
    ids=["first-frame", "second-frame"],
)
def test_a_zstd_window_above_the_http_limit_is_refused(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    at_limit: bytes,
    above_limit: bytes,
    declared_size: int | None,
    frame_bytes: int,
    prefix: bytes,
    decoded_size: int,
    prefix_bytes: int,
) -> None:
    assert (_fixture_header(at_limit), _fixture_header(above_limit)) == (
        (8_388_608, declared_size),
        (16_777_216, declared_size),
    )
    (tmp_path / "at-limit.zst").write_bytes(prefix + at_limit)
    (tmp_path / "large-window.zst").write_bytes(prefix + above_limit)
    server = fixture_site(
        Site(
            root=tmp_path,
            routes={
                "/": Page(
                    body='<script src="/at-limit.js"></script>'
                    '<script src="/large-window.js"></script>',
                ),
                "/at-limit.js": Page(
                    file="at-limit.zst",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "zstd")],
                ),
                "/large-window.js": Page(
                    file="large-window.zst",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "zstd")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"), "--retries", "0")

    accepted = server.url("/at-limit.js")
    refused = server.url("/large-window.js")
    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error, size_bytes, body_truncated FROM urls WHERE url = ?",
        [refused],
    ) == [("error", "invalid_response", None, None)]
    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error, size_bytes, transferred_bytes, content_encoding, "
        "body_truncated FROM urls WHERE url = ?",
        [accepted],
    ) == [("fetched", None, decoded_size, prefix_bytes + frame_bytes, "zstd", 0)]


@pytest.mark.parametrize("chunk_size", [32, 19], ids=["whole-stream", "split-second-header"])
async def test_an_oversized_zstd_window_is_refused_below_the_body_cap(chunk_size: int) -> None:
    # Both frames would decode to ten bytes total, and all 32 wire bytes fit the body cap.
    # A 19-byte first chunk ends just before the second window descriptor.
    accepted = WINDOW_8_MIB + WINDOW_8_MIB_WITH_SIZE
    refused = WINDOW_8_MIB + WINDOW_16_MIB_WITH_SIZE

    body = await read_body(_chunks(accepted, chunk_size), "zstd", limit=64)
    assert (body.data, body.truncated, body.transferred_bytes) == (b"hellohello", False, 32)

    with pytest.raises(BodyDecodingError):
        await read_body(_chunks(refused, chunk_size), "zstd", limit=64)


async def test_the_window_limit_includes_the_descriptor_mantissa() -> None:
    assert _fixture_header(WINDOW_9_MIB_WITH_SIZE) == (9_437_184, 5)

    with pytest.raises(BodyDecodingError):
        await read_body(_chunks(WINDOW_9_MIB_WITH_SIZE, 18), "zstd", limit=64)


async def test_a_single_segment_uses_the_content_size_as_its_window() -> None:
    # A four-byte zero dictionary ID precedes the size. Each RLE block yields 128 KiB of x.
    block = bytes.fromhex("020010 78")
    at_limit = bytes.fromhex("28b52ffd a3 00000000 00008000") + block * 63
    at_limit += bytes.fromhex("030010 78")
    above_limit = bytes.fromhex("28b52ffd a3 00000000 01008000") + block * 64
    above_limit += bytes.fromhex("0b0000 78")

    # End the first read inside Frame_Content_Size. Both valid streams fit the wire cap.
    body = await read_body(_pieces(at_limit[:12], at_limit[12:]), "zstd", limit=512)
    assert (body.data, body.truncated, body.transferred_bytes) == (b"x" * 512, True, 269)

    with pytest.raises(BodyDecodingError):
        await read_body(_pieces(above_limit[:12], above_limit[12:]), "zstd", limit=512)


async def _chunks(data: bytes, size: int) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


async def _pieces(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part
