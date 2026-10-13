"""The synthetic site of the 500k benchmark (026-add-parse-pool D6)."""

import http.client
import re
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.server import ServerHandle
from tests.fixture_site.synthetic.site import NO_FAULTS, SyntheticSite, page_path

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


LINK_TYPES = {
    "hyperlink",
    "canonical",
    "pagination",
    "hreflang",
    "iframe",
    "meta_refresh",
    "http_refresh",
    "image",
    "css",
    "javascript",
    "video",
    "audio",
    "media",
    "amphtml",
    "mobile_alternate",
    "misc",
}


class LinkReader(HTMLParser):
    """The Link types of docs/crawling.md (020), read with the stdlib parser, one per Link."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self._media: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {name: value or "" for name, value in attrs}
        rel = set(a.get("rel", "").lower().split())
        if tag in {"video", "audio"}:
            self._media.append(tag)
        if tag in {"a", "area"} and "href" in a:
            self.links.append("hyperlink")
        elif tag == "link" and "href" in a:
            self.links.append(link_rel_type(rel, a))
        elif tag in {"iframe", "frame"} and "src" in a:
            self.links.append("iframe")
        elif tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.links.append("meta_refresh")
        elif tag == "script" and "src" in a:
            self.links.append("javascript")
        elif tag in {"embed", "object"} and ("src" in a or "data" in a):
            self.links.append("media")
        self._media_links(tag, a)

    def _media_links(self, tag: str, a: dict[str, str]) -> None:
        if tag in {"img", "source"} and "srcset" in a:
            self.links += ["image"] * len(a["srcset"].split(","))
        if tag == "img" and "src" in a:
            self.links.append("image")
        if tag == "video" and "poster" in a:
            self.links.append("image")
        if tag in {"video", "audio"} and "src" in a:
            self.links.append(tag)
        if tag in {"source", "track"} and "src" in a and self._media:
            self.links.append(self._media[-1])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"video", "audio"} and self._media:
            self._media.pop()


def link_rel_type(rel: set[str], a: dict[str, str]) -> str:
    if "canonical" in rel:
        return "canonical"
    if rel & {"next", "prev", "previous"}:
        return "pagination"
    if "alternate" in rel and "hreflang" in a:
        return "hreflang"
    if "alternate" in rel and "media" in a:
        return "mobile_alternate"
    if "stylesheet" in rel:
        return "css"
    if "amphtml" in rel:
        return "amphtml"
    return "misc"


def links_of(fetched: Fetched) -> list[str]:
    reader = LinkReader()
    reader.feed(fetched.body.decode("utf-8", "replace"))
    return reader.links + (["http_refresh"] if "refresh" in fetched.headers else [])


def test_the_pages_carry_a_link_of_every_link_type(fixture_site: StartSite) -> None:
    server = fixture_site(SyntheticSite(seed=1, pages=1_000, shares=NO_FAULTS).as_site())

    connection = connect(server)
    try:
        types = {kind for n in range(100) for kind in links_of(fetch(connection, page_path(n)))}
    finally:
        connection.close()

    assert types == LINK_TYPES


def test_a_page_with_children_is_about_50_kb_with_about_450_links(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(SyntheticSite(seed=1, pages=100_000, shares=NO_FAULTS).as_site())

    connection = connect(server)
    try:
        page = fetch(connection, "/p/1")
    finally:
        connection.close()

    size, links = len(page.body), len(links_of(page))
    assert (45_000 <= size <= 55_000, 400 <= links <= 500) == (True, True), (size, links)


def test_every_page_is_reached_from_the_seed_by_its_hyperlinks(fixture_site: StartSite) -> None:
    site = SyntheticSite(seed=1, pages=600, fanout=5, shares=NO_FAULTS)
    server = fixture_site(site.as_site())

    reached = crawl(server)

    assert {path for path, got in reached.items() if got.status == 200} == page_paths(600)
