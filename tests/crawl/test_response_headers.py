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
                # The connection drops before any response: the URL gets no row.
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
