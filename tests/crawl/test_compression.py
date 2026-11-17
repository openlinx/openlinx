"""Verify compressed responses over HTTP."""

from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.fixture_site.sites.exact import site as exact
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

SHOP = Site(
    {
        "/robots.txt": Robots("User-agent: *\nDisallow: /cart\n"),
        "/": Page(body='<title>Shop</title><a href="/shoes">Shoes</a>'),
        "/shoes": Page(body="<title>Shoes</title>"),
    }
)


def test_requests_accept_compressed_bodies(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SHOP)

    crawled(server.url("/"))

    assert {
        request.path: request.headers.get("Accept-Encoding") for request in server.requests
    } == {
        "/robots.txt": "gzip, deflate, br, zstd",
        "/": "gzip, deflate, br, zstd",
        "/shoes": "gzip, deflate, br, zstd",
    }


def test_a_compressed_resource_records_both_sizes(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            root=exact.SITE.root,
            routes={
                "/": Page(body='<title>Shop</title><script src="/app.js"></script>'),
                "/app.js": exact.SITE.routes["/app.js"],
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT size_bytes, transferred_bytes, content_encoding FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [(10000, 2500, "gzip")]


@pytest.mark.parametrize(
    ("override", "wire"),
    [
        ([], "gzip, deflate, br, zstd"),
        (["--header", "Accept-Encoding: identity"], "identity"),
        (["--header", "Accept-Encoding: identity, zstd;q=0"], "identity, zstd;q=0"),
    ],
    ids=["default", "unadvertised", "q-zero"],
)
def test_a_zstd_resource_records_both_sizes(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    override: list[str],
    wire: str,
) -> None:
    (tmp_path / "app.js.zst").write_bytes(bytes.fromhex("28b52ffd200529000068656c6c6f"))
    server = fixture_site(
        Site(
            root=tmp_path,
            routes={
                "/": Page(body='<script src="/app.js"></script>'),
                "/app.js": Page(
                    file="app.js.zst",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "zstd")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"), *override)

    assert query(
        crawl_file,
        "SELECT fetch_state, size_bytes, transferred_bytes, content_encoding, body_truncated"
        " FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [("fetched", 5, 14, "zstd", 0)]
    assert {
        request.path: request.headers.getall("Accept-Encoding") for request in server.requests
    } == {
        "/robots.txt": [wire],
        "/": [wire],
        "/app.js": [wire],
    }


def test_stacked_encodings_are_decoded_in_reverse_order(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            root=exact.SITE.root,
            routes={
                "/": Page(body='<title>Shop</title><script src="/app.js"></script>'),
                "/app.js": exact.SITE.routes["/app.js.gz.br"],
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT size_bytes, content_encoding FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [(10000, "gzip, br")]


def test_a_corrupt_compressed_body_is_an_invalid_response(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><script src="/broken.js"></script>'),
                # A build step that set the header but shipped the script uncompressed.
                "/broken.js": Page(
                    body="document.querySelector('.cart-count').textContent = 0;",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "gzip")],
                ),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--retries", "0")

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error FROM urls WHERE url = ?",
        [server.url("/broken.js")],
    ) == [("error", "invalid_response")]


def test_a_body_in_an_encoding_that_was_not_offered_is_not_parsed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/unknown.html">Unknown</a>'),
                "/unknown.html": Page(
                    body="<title>Unknown coding</title>",
                    headers=[("Content-Encoding", "x-unknown")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, parsed, parse_error, size_bytes FROM urls WHERE url = ?",
        [server.url("/unknown.html")],
    ) == [("fetched", 0, "unsupported_encoding", None)]


def test_codings_on_repeated_header_lines_are_decoded_as_one_list(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A proxy that adds its own Content-Encoding line instead of extending the server's.
    server = fixture_site(
        Site(
            root=exact.SITE.root,
            routes={
                "/": Page(body='<title>Shop</title><script src="/app.js"></script>'),
                "/app.js": Page(
                    file="app.js.gz.br",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "gzip"), ("Content-Encoding", "br")],
                ),
            },
        )
    )
    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT size_bytes, content_encoding FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [(10000, "gzip, br")]
