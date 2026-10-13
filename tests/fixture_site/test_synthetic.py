"""The synthetic site of the 500k benchmark (026-add-parse-pool D6)."""

import http.client
import re
from collections import deque
from dataclasses import dataclass

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.server import ServerHandle
from tests.fixture_site.synthetic.site import NO_FAULTS, SyntheticSite

HYPERLINK = re.compile(rb'<a href="(/[^"]*)"')


@dataclass(frozen=True)
class Fetched:
    status: int
    headers: dict[str, str]
    body: bytes


def fetch(connection: http.client.HTTPConnection, path: str) -> Fetched:
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    return Fetched(response.status, {k.lower(): v for k, v in response.getheaders()}, body)


def connect(server: ServerHandle) -> http.client.HTTPConnection:
    host, port = server.base_url.removeprefix("http://").split(":")
    return http.client.HTTPConnection(host, int(port), timeout=60)


def crawl(server: ServerHandle) -> dict[str, Fetched]:
    """Every path reached from / through <a href>, as an independent client sees it."""
    connection = connect(server)
    reached: dict[str, Fetched] = {}
    queue = deque(["/"])
    try:
        while queue:
            path = queue.popleft()
            if path in reached:
                continue
            reached[path] = fetched = fetch(connection, path)
            queue.extend(href.decode() for href in HYPERLINK.findall(fetched.body))
    finally:
        connection.close()
    return reached


def page_paths(pages: int) -> set[str]:
    return {"/"} | {f"/p/{n}" for n in range(1, pages)}


def test_every_page_is_reached_from_the_seed_by_its_hyperlinks(fixture_site: StartSite) -> None:
    site = SyntheticSite(seed=1, pages=600, fanout=5, shares=NO_FAULTS)
    server = fixture_site(site.as_site())

    reached = crawl(server)

    assert {path for path, got in reached.items() if got.status == 200} == page_paths(600)
