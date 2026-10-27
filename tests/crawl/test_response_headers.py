"""Response headers (022-add-fetch-policy D7, fetching spec: The response_headers table)."""

import json

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_response_headers_are_stored_as_received(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Spring sale preview</title><a href="/stock">Stock</a>',
                    headers=[("X-Robots-Tag", "noindex")],
                ),
                # The connection resets inside the body: the URL is an error, without a response,
                # so it gets no row.
                "/stock": Page(body="<p>In stock</p>", reset_after=0),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--retries", "0")

    rows = query(
        crawl_file,
        "SELECT urls.url, response_headers.headers FROM response_headers "
        "JOIN urls ON urls.id = response_headers.url_id",
    )
    assert [(url, ["X-Robots-Tag", "noindex"] in json.loads(headers)) for url, headers in rows] == [
        (server.url("/"), True)
    ]


def test_a_cookie_value_is_not_stored(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body="<title>Your basket</title>",
                    headers=[("Set-Cookie", "sid=abc123; Path=/; HttpOnly")],
                )
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    ((headers,),) = query(
        crawl_file,
        "SELECT headers FROM response_headers JOIN urls ON urls.id = response_headers.url_id "
        "WHERE urls.url = ?",
        [server.url("/")],
    )
    # The crawl file with its -wal and -shm files, whatever the writer left in each.
    files = crawl_file.parent.glob(f"{crawl_file.name}*")
    assert (
        ["Set-Cookie", "sid=***; Path=/; HttpOnly"] in json.loads(headers),
        [file.name for file in files if b"abc123" in file.read_bytes()],
    ) == (True, [])


def test_headers_are_stored_in_the_order_received(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body="<title>Your account</title>",
                    headers=[
                        ("Set-Cookie", "sid=abc123; Path=/; HttpOnly"),
                        ("X-Frame-Options", "DENY"),
                        ("Set-Cookie", "theme=dark; Max-Age=31536000"),
                    ],
                )
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    ((headers,),) = query(crawl_file, "SELECT headers FROM response_headers")
    assert [
        pair for pair in json.loads(headers) if pair[0] in {"Set-Cookie", "X-Frame-Options"}
    ] == [
        ["Set-Cookie", "sid=***; Path=/; HttpOnly"],
        ["X-Frame-Options", "DENY"],
        ["Set-Cookie", "theme=***; Max-Age=31536000"],
    ]
