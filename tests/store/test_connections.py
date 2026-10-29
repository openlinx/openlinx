"""Crawl file URIs (design D2 of 015-add-crawl-store)."""

from pathlib import PurePath, PurePosixPath, PureWindowsPath

import pytest

from openlinx.store.connections import file_uri


@pytest.mark.parametrize(
    ("path", "uri"),
    [
        (PurePosixPath("/home/ann/site/c.sqlite"), "file:///home/ann/site/c.sqlite"),
        (PureWindowsPath(r"C:\site\.openlinx\c.sqlite"), "file:///C:/site/.openlinx/c.sqlite"),
        (
            PureWindowsPath(r"\\fileserver\share\site\c.sqlite"),
            "file:////fileserver/share/site/c.sqlite",
        ),
        (
            PurePosixPath("/home/ann/a b #1 ?x 100% é.sqlite"),
            "file:///home/ann/a%20b%20%231%20%3Fx%20100%25%20%C3%A9.sqlite",
        ),
    ],
)
def test_crawl_file_uris(path: PurePath, uri: str) -> None:
    assert file_uri(path) == uri
