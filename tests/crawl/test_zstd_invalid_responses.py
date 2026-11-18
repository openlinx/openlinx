"""Classify incomplete and corrupt zstd Resources over real HTTP."""

from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# The frames with and without a checksum both contain the raw block "hello".
HELLO = bytes.fromhex("28b52ffd 20 05 290000 68656c6c6f")
INCOMPLETE = bytes.fromhex("28b52ffd 20 05 290000 68656c6c")
CHECKSUMMED = bytes.fromhex("28b52ffd 24 05 290000 68656c6c6f a36d9f88")
BAD_CHECKSUM = bytes.fromhex("28b52ffd 24 05 290000 68656c6c6f a36d9f89")
# The last block uses reserved type 3 where HELLO uses raw type 0.
RESERVED_BLOCK = bytes.fromhex("28b52ffd 20 05 2f0000 68656c6c6f")


def test_an_incomplete_zstd_frame_is_an_invalid_response(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    _check_pair(fixture_site, tmp_path, INCOMPLETE, HELLO, decoded_size=5, wire_size=14)


@pytest.mark.parametrize(
    ("broken", "valid", "decoded_size", "wire_size"),
    [
        pytest.param(BAD_CHECKSUM, CHECKSUMMED, 5, 18, id="wrong-checksum"),
        pytest.param(RESERVED_BLOCK, HELLO, 5, 14, id="reserved-block"),
        pytest.param(HELLO + b"not-zstd", HELLO, 5, 14, id="trailing-garbage"),
        pytest.param(
            CHECKSUMMED + INCOMPLETE, CHECKSUMMED + HELLO, 10, 32, id="incomplete-second-frame"
        ),
    ],
)
def test_a_damaged_zstd_stream_is_an_invalid_response(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    broken: bytes,
    valid: bytes,
    decoded_size: int,
    wire_size: int,
) -> None:
    _check_pair(
        fixture_site,
        tmp_path,
        broken,
        valid,
        decoded_size=decoded_size,
        wire_size=wire_size,
    )


def _check_pair(
    fixture_site: StartSite,
    directory: Path,
    broken: bytes,
    valid: bytes,
    *,
    decoded_size: int,
    wire_size: int,
) -> None:
    (directory / "broken.zst").write_bytes(broken)
    (directory / "control.zst").write_bytes(valid)
    server = fixture_site(
        Site(
            root=directory,
            routes={
                "/": Page(
                    body='<script src="/broken.js"></script><script src="/control.js"></script>',
                ),
                "/broken.js": Page(
                    file="broken.zst",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "zstd")],
                ),
                "/control.js": Page(
                    file="control.zst",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "zstd")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error, attempt_count, size_bytes, transferred_bytes, "
        "body_truncated FROM urls WHERE url IN (?, ?) ORDER BY url",
        [server.url("/broken.js"), server.url("/control.js")],
    ) == [
        ("error", "invalid_response", 1, None, None, None),
        ("fetched", None, 1, decoded_size, wire_size, 0),
    ]
