"""The synthetic site of the 500k benchmark (026-add-parse-pool D6)."""

import http.client
import os
import re
import subprocess
import sys
import time
import tracemalloc
from collections import Counter, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.server import ServerHandle
from tests.fixture_site.synthetic.serve import SiteProcess, Tally
from tests.fixture_site.synthetic.site import NO_FAULTS, Fault, SyntheticSite, page_path

HYPERLINK = re.compile(rb'<a href="(/[^"]*)"')
END_WORKER = b'<meta name="spider-benchmark" content="end-worker">'


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


def connect(base_url: str) -> http.client.HTTPConnection:
    host, port = base_url.removeprefix("http://").split(":")
    return http.client.HTTPConnection(host, int(port), timeout=60)


def crawl(server: ServerHandle) -> dict[str, Fetched]:
    """Every path reached from / through <a href>, as an independent client sees it."""
    connection = connect(server.base_url)
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


def is_page(path: str) -> bool:
    return path == "/" or path.startswith("/p/")


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
RESOURCE_TYPES = {"image", "css", "javascript", "video", "audio", "media"}
NOT_FOLLOWED_TYPES = {"amphtml", "mobile_alternate", "misc"}


class LinkReader(HTMLParser):
    """The Links of docs/crawling.md's table (020), read with the stdlib parser: (type, URL)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._media: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {name: value or "" for name, value in attrs}
        rel = set(a.get("rel", "").lower().split())
        if tag in {"video", "audio"}:
            self._media.append(tag)
        if tag in {"a", "area"} and "href" in a:
            self.links.append(("hyperlink", a["href"]))
        elif tag == "link" and "href" in a:
            self.links.append((link_rel_type(rel, a), a["href"]))
        elif tag in {"iframe", "frame"} and "src" in a:
            self.links.append(("iframe", a["src"]))
        elif tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.links.append(("meta_refresh", a["content"].partition("url=")[2]))
        elif tag == "script" and "src" in a:
            self.links.append(("javascript", a["src"]))
        elif tag in {"embed", "object"} and ("src" in a or "data" in a):
            self.links.append(("media", a.get("src") or a["data"]))
        self._media_links(tag, a)

    def _media_links(self, tag: str, a: dict[str, str]) -> None:
        if tag in {"img", "source"} and "srcset" in a:
            self.links += [("image", c.split()[0]) for c in a["srcset"].split(",")]
        if tag == "img" and "src" in a:
            self.links.append(("image", a["src"]))
        if tag == "video" and "poster" in a:
            self.links.append(("image", a["poster"]))
        if tag in {"video", "audio"} and "src" in a:
            self.links.append((tag, a["src"]))
        if tag in {"source", "track"} and "src" in a and self._media:
            self.links.append((self._media[-1], a["src"]))

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


def links_of(fetched: Fetched) -> list[tuple[str, str]]:
    reader = LinkReader()
    reader.feed(fetched.body.decode("utf-8", "replace"))
    refresh = fetched.headers.get("refresh")
    return reader.links + ([] if refresh is None else [("http_refresh", refresh.split("url=")[1])])


def test_the_pages_carry_a_link_of_every_link_type(fixture_site: StartSite) -> None:
    server = fixture_site(SyntheticSite(seed=1, pages=1_000, shares=NO_FAULTS).as_site())

    connection = connect(server.base_url)
    try:
        pages = [fetch(connection, page_path(n)) for n in range(100)]
    finally:
        connection.close()

    assert {kind for page in pages for kind, _ in links_of(page)} == LINK_TYPES


def test_a_page_with_children_is_about_50_kb_with_about_450_links(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(SyntheticSite(seed=1, pages=100_000, shares=NO_FAULTS).as_site())

    connection = connect(server.base_url)
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


def observed_fault(page: Fetched) -> str | None:
    """The fault a client sees in a response, from the response alone."""
    if page.status == 500:
        return "server_error"
    if b"<div>" * 1_000 in page.body:
        return "nested_divs"
    if END_WORKER in page.body:
        return "ends_worker"
    if "charset=nonsense" in page.headers["content-type"]:
        return "unknown_charset"
    try:
        page.body.decode("utf-8")
    except UnicodeDecodeError:
        try:
            page.body.decode("cp1251")
        except UnicodeDecodeError:
            return "invalid_utf8"
        return "wrong_charset"
    if b"\x00" in page.body:
        return "malformed_html"
    if b"<title>" not in page.body:
        return "no_title"
    if b"<h1>" not in page.body:
        return "no_h1"
    return None


LOSES_LINKS = {"server_error", "nested_divs", "ends_worker"}
# A slow Page looks like any other but for its time, which a timing test bounds only from below.
SEEN_FAULTS = [fault for fault in Fault if fault is not Fault.SLOW]
FAULTY = SyntheticSite(seed=3, pages=400, fanout=4, shares=dict.fromkeys(SEEN_FAULTS, 0.05))


@pytest.fixture(scope="module")
def faulty_crawl(module_fixture_site: StartSite) -> dict[str, Fetched]:
    return crawl(module_fixture_site(FAULTY.as_site()))


def test_the_faults_a_client_sees_are_the_counts_of_the_manifest(
    faulty_crawl: dict[str, Fetched],
) -> None:
    seen = Counter(observed_fault(got) for path, got in faulty_crawl.items() if is_page(path))

    counts = {fault.value: seen[fault.value] for fault in Fault}
    least = min(counts[fault.value] for fault in SEEN_FAULTS)
    assert (counts, least > 0) == (FAULTY.manifest()["faults"], True)


def test_the_urls_the_pages_reference_are_the_url_totals_of_the_manifest(
    faulty_crawl: dict[str, Fetched],
) -> None:
    links = [
        link
        for path, got in faulty_crawl.items()
        if is_page(path) and observed_fault(got) not in LOSES_LINKS
        for link in links_of(got)
    ]
    followed = {url for kind, url in links if kind not in NOT_FOLLOWED_TYPES}
    totals: dict[str, Any] = {
        "pages": sum(1 for path, got in faulty_crawl.items() if is_page(path)),
        "resources": len({url for kind, url in links if kind in RESOURCE_TYPES}),
        "not_followed": len({u for k, u in links if k in NOT_FOLLOWED_TYPES} - followed),
        "missing": sum(
            1 for url in followed if url in faulty_crawl and faulty_crawl[url].status == 404
        ),
    }
    totals["total"] = sum(totals.values())

    assert totals == FAULTY.manifest()["urls"]


def test_the_manifest_names_the_outcome_each_fault_leaves_in_urls() -> None:
    outcomes = SyntheticSite(seed=1, pages=10).manifest()["outcomes"]

    assert (outcomes["nested_divs"], outcomes["ends_worker"], outcomes["server_error"]) == (
        {"status_code": 200, "parsed": 0, "parse_error": "parse_timeout"},
        {"status_code": 200, "parsed": 0, "parse_error": "worker_crashed"},
        {"status_code": 500, "parsed": 0, "parse_error": None},
    )


# Renders a few Pages of every kind and the manifest, and prints one digest of them all.
DIGEST_IN_A_CHILD = (
    "import hashlib, json\n"
    "from tests.fixture_site.synthetic.site import Fault, SyntheticSite\n"
    "site = SyntheticSite(seed=3, pages=400, fanout=4, shares=dict.fromkeys(Fault, 0.05))\n"
    "digest = hashlib.sha256(json.dumps(site.manifest(), sort_keys=True).encode())\n"
    "for n in range(0, 400, 3):\n"
    "    digest.update(site.render(n))\n"
    "print(digest.hexdigest())\n"
)


def digest_in_a_child(hash_seed: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", DIGEST_IN_A_CHILD],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        check=True,
        text=True,
        timeout=60,
    ).stdout


@pytest.mark.slow
def test_the_same_seed_gives_the_same_bytes_in_every_process() -> None:
    assert digest_in_a_child("1") == digest_in_a_child("2")


def test_another_seed_places_the_faults_on_other_pages() -> None:
    shares = dict.fromkeys(Fault, 0.05)
    placed = [
        [SyntheticSite(seed=seed, pages=400, fanout=4, shares=shares).fault(n) for n in range(400)]
        for seed in (3, 4)
    ]

    assert placed[0] != placed[1]


@pytest.mark.parametrize(
    "changes",
    [
        {"pages": 0},
        {"fanout": 0},
        {"shares": {Fault.NO_TITLE: -0.1}},
        {"shares": {Fault.NO_TITLE: 0.6, Fault.NO_H1: 0.5}},
    ],
)
def test_a_synthetic_site_is_checked_when_it_is_declared(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="synthetic site"):
        SyntheticSite(**{"seed": 1, "pages": 10, **changes})


def elapsed(server: ServerHandle, path: str) -> float:
    connection = connect(server.base_url)
    try:
        started = time.monotonic()
        fetch(connection, path)
        return time.monotonic() - started
    finally:
        connection.close()


def test_a_slow_page_answers_no_sooner_than_its_delay(fixture_site: StartSite) -> None:
    site = SyntheticSite(seed=1, pages=20, fanout=4, shares={Fault.SLOW: 1.0}, slow_seconds=0.5)
    slow = next(n for n in range(20) if site.fault(n) is Fault.SLOW)
    server = fixture_site(site.as_site())

    assert elapsed(server, page_path(slow)) >= 0.5


@pytest.mark.parametrize("path", ["/", "/r/i/0.jpg"])
def test_the_latency_delays_every_response(fixture_site: StartSite, path: str) -> None:
    server = fixture_site(SyntheticSite(seed=1, pages=20, shares=NO_FAULTS, latency=0.3).as_site())

    assert elapsed(server, path) >= 0.3


def test_the_manifest_keeps_nothing_per_page() -> None:
    # 50,000 Pages, not 500,000: tracemalloc slows the pass about thirtyfold.
    site = SyntheticSite(seed=1, pages=50_000)

    tracemalloc.start()
    try:
        site.manifest()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 256 * 2**10


@pytest.mark.slow
def test_the_site_process_tallies_the_requests_it_served() -> None:
    with SiteProcess(SyntheticSite(seed=1, pages=20, shares=NO_FAULTS)) as process:
        connection = connect(process.base_url)
        try:
            for path in ("/", "/p/1", "/p/1", "/r/i/0.jpg", "/nope"):
                fetch(connection, path)
        finally:
            connection.close()
        tally = process.stop()

    assert tally == Tally(
        pages_requested=2,
        pages_requested_more_than_once=1,
        resource_requests=1,
        not_found=1,
    )
