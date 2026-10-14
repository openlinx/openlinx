"""A seeded synthetic site of up to 500,000 Pages, computed per request (026-add-parse-pool D6)."""

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

from tests.fixture_site.routes import Bytes, Route, Site, Status

HTML = "text/html; charset=utf-8"
TEMPLATES = 4
NAV_LINKS = 200
FOOTER_REPEATS = 80
RANDOM_LINKS = 60
IMAGES_PER_PAGE = 20
HREFLANGS = ("de", "fr", "es", "it")
TARGET_SIZE = 50_000
PARAGRAPH = 600
# Every 50th Page from the first carries a meta refresh, from the second an HTTP Refresh header.
REFRESH_EVERY = 50

WORDS = [
    "crawl",
    "index",
    "page",
    "link",
    "anchor",
    "title",
    "heading",
    "content",
    "section",
    "topic",
    "guide",
    "news",
    "shop",
    "docs",
    "blog",
    "review",
    "price",
    "offer",
    "delivery",
    "service",
    "support",
    "account",
    "search",
    "result",
    "filter",
    "category",
    "product",
    "feature",
    "compare",
    "market",
    "report",
    "update",
    "release",
    "summary",
    "detail",
    "overview",
    "article",
    "question",
    "answer",
    "reason",
    "example",
    "method",
    "result",
    "source",
    "image",
    "video",
    "audio",
    "stream",
    "schedule",
]
CORPUS = " ".join(WORDS[(i * 7_919) % len(WORDS)] for i in range(20_000))


class Fault(StrEnum):
    NESTED_DIVS = "nested_divs"
    ENDS_WORKER = "ends_worker"
    SERVER_ERROR = "server_error"
    INVALID_UTF8 = "invalid_utf8"
    WRONG_CHARSET = "wrong_charset"
    UNKNOWN_CHARSET = "unknown_charset"
    MALFORMED_HTML = "malformed_html"
    SLOW = "slow"
    NO_TITLE = "no_title"
    NO_H1 = "no_h1"
    # Added last: the draw order follows the enum, so a new kind moves no other fault.
    RESET = "reset"


NO_FAULTS: Mapping[Fault, float] = {}
DEFAULT_SHARES: Mapping[Fault, float] = {
    Fault.NESTED_DIVS: 1e-5,
    Fault.ENDS_WORKER: 1e-5,
    Fault.SERVER_ERROR: 1e-3,
    Fault.INVALID_UTF8: 5e-4,
    Fault.WRONG_CHARSET: 5e-4,
    Fault.UNKNOWN_CHARSET: 5e-4,
    Fault.MALFORMED_HTML: 1e-3,
    Fault.SLOW: 2e-4,
    Fault.NO_TITLE: 2e-3,
    Fault.NO_H1: 2e-3,
    Fault.RESET: 2e-4,
}
# Their Links are lost: the Page is not parsed, or its preparation never ends.
LOSES_LINKS = frozenset({Fault.NESTED_DIVS, Fault.ENDS_WORKER, Fault.SERVER_ERROR, Fault.RESET})
FETCHED = {"fetch_state": "fetched", "fetch_error": None}
PARSED = {**FETCHED, "status_code": 200, "parsed": 1, "parse_error": None}
# What each fault should leave in `urls`; the Pages over the deadline and those that end their
# worker are contained only by 026's pool.
OUTCOMES: Mapping[Fault, Mapping[str, Any]] = {
    Fault.NESTED_DIVS: {**FETCHED, "status_code": 200, "parsed": 0, "parse_error": "parse_timeout"},
    Fault.ENDS_WORKER: {
        **FETCHED,
        "status_code": 200,
        "parsed": 0,
        "parse_error": "worker_crashed",
    },
    Fault.SERVER_ERROR: {**FETCHED, "status_code": 500, "parsed": 0, "parse_error": None},
    Fault.RESET: {
        "fetch_state": "error",
        "fetch_error": "connection_error",
        "status_code": None,
        "parsed": 0,
        "parse_error": None,
    },
    **dict.fromkeys(
        (
            Fault.INVALID_UTF8,
            Fault.WRONG_CHARSET,
            Fault.UNKNOWN_CHARSET,
            Fault.MALFORMED_HTML,
            Fault.SLOW,
            Fault.NO_TITLE,
            Fault.NO_H1,
        ),
        PARSED,
    ),
}
# The marker on which the benchmark's own extractor ends its worker process.
END_WORKER = '<meta name="spider-benchmark" content="end-worker">'
# 100,000 levels take lexbor about 80 s of CPU, far over the 30 s deadline (design D8).
NESTED_DEPTH = 100_000
CYRILLIC = bytes(range(0xC0, 0x100)).decode("cp1251")
INVALID_BYTES = b"<p>broken \x98\xff\xfe bytes</p>"
# Bytes of the body sent before the connection is reset: the headers and the start of the Page.
RESET_AFTER = 4_096
MALFORMED = b'<div class="open><p>nul\x00byte<table><td>cell<b><i>misnested</b></i>'


class Link(NamedTuple):
    target: str
    type: str
    element: str
    attribute: str
    anchor: str | None = None


@dataclass(frozen=True)
class Pool:
    """A bounded set of shared URLs, so their number does not grow with the Pages."""

    name: str
    size: int
    path: str
    content_type: str
    # What a Crawl does with it: "resource" (checked), "not_followed", "missing" (a 404) or
    # "external" (checked on another host).
    kind: str
    # Spread over this many External hosts, or 0 for the site's own host.
    hosts: int = 0

    def url(self, index: int) -> str:
        path = self.path.format(index)
        return f"http://{external_host(index % self.hosts)}{path}" if self.hosts else path


def external_host(k: int) -> str:
    return f"ext{k}.test"


IMAGES = Pool("images", 1_500, "/r/i/{}.jpg", "image/jpeg", "resource")
STYLESHEETS = Pool("stylesheets", TEMPLATES * 8, "/r/c/{}.css", "text/css", "resource")
SCRIPTS = Pool("scripts", TEMPLATES * 10, "/r/j/{}.js", "text/javascript", "resource")
VIDEOS = Pool("videos", 100, "/r/v/{}.mp4", "video/mp4", "resource")
AUDIOS = Pool("audios", 100, "/r/a/{}.mp3", "audio/mpeg", "resource")
MEDIA = Pool("media", 100, "/r/m/{}.pdf", "application/pdf", "resource")
AMP = Pool("amp", 100, "/amp/{}", HTML, "not_followed")
MOBILE = Pool("mobile", 100, "/m/{}", HTML, "not_followed")
MISC = Pool("misc", 3, "/misc/{}", "application/octet-stream", "not_followed")
MISSING = Pool("missing", 100, "/missing/{}", HTML, "missing")
# Reached through the DNS resolver hook, which sends every External host to this site.
EXTERNAL = Pool("external", 1_000, "/e/{}", HTML, "external", hosts=50)
EXTERNAL_HOSTS = tuple(external_host(k) for k in range(EXTERNAL.hosts))
EXTERNAL_PER_PAGE = 5
POOLS = (IMAGES, STYLESHEETS, SCRIPTS, VIDEOS, AUDIOS, MEDIA, AMP, MOBILE, MISC, MISSING, EXTERNAL)
SERVED_POOLS = tuple(pool for pool in POOLS if pool is not MISSING)
MISC_RELS = ("icon", "manifest", "alternate")


def page_path(n: int) -> str:
    return "/" if n == 0 else f"/p/{n}"


def page_number(path: str, pages: int) -> int | None:
    if path == "/":
        return 0
    return _number(path.removeprefix("/p/"), pages) if path.startswith("/p/") else None


def _number(digits: str, below: int) -> int | None:
    if not digits.isdigit() or str(int(digits)) != digits:
        return None
    n = int(digits)
    return n if n < below else None


def pool_index(path: str) -> tuple[Pool, int] | None:
    """The pool URL at `path` and its index, or None."""
    for pool in POOLS:
        prefix, _, suffix = pool.path.partition("{}")
        if path.startswith(prefix) and path.endswith(suffix):
            index = _number(path[len(prefix) : len(path) - len(suffix)], pool.size)
            if index is not None:
                return pool, index
    return None


def _pool_route(path: str, delay: float) -> Route | None:
    found = pool_index(path)
    if found is None or found[0] not in SERVED_POOLS:
        return None
    pool, index = found
    body = f"{pool.name} {index}".encode()
    return Bytes(body, content_type=pool.content_type, delay=delay)


def pool_refs(n: int) -> Iterator[tuple[Pool, tuple[int, ...]]]:
    """The shared URLs Page n references, by pool, in the order the Page renders them."""
    template = n % TEMPLATES
    yield MOBILE, (n % MOBILE.size,)
    yield AMP, (n % AMP.size,)
    yield MISC, tuple(range(MISC.size))
    yield STYLESHEETS, tuple(range(template * 8, template * 8 + 8))
    yield SCRIPTS, tuple(range(template * 10, template * 10 + 10))
    first = n * IMAGES_PER_PAGE
    yield IMAGES, tuple((first + j) % IMAGES.size for j in range(IMAGES_PER_PAGE))
    yield VIDEOS, (n % VIDEOS.size,)
    yield AUDIOS, (n % AUDIOS.size,)
    yield MEDIA, ((2 * n) % MEDIA.size, (2 * n + 1) % MEDIA.size)
    yield MISSING, (n % MISSING.size,)
    first = n * EXTERNAL_PER_PAGE
    yield EXTERNAL, tuple((first + j) % EXTERNAL.size for j in range(EXTERNAL_PER_PAGE))


_MASK = 2**64 - 1


def _stream(seed: int, n: int, purpose: str) -> Iterator[int]:
    """splitmix64 from a blake2b seed: the same numbers on every Python and OS."""
    digest = hashlib.blake2b(f"{seed}:{n}:{purpose}".encode(), digest_size=8).digest()
    state = int.from_bytes(digest)
    while True:
        state = (state + 0x9E3779B97F4A7C15) & _MASK
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        yield z ^ (z >> 31)


def _nested(n: int) -> bytes:
    head = f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Deep {n}</title>'
    body = f"</head><body><h1>Deep {n}</h1>{'<div>' * NESTED_DEPTH}{'</div>' * NESTED_DEPTH}"
    return f"{head}{body}</body></html>\n".encode()


class _Page:
    """The HTML of one Page and its Links, built side by side so they always agree."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.links: list[Link] = []

    def add(self, html: str, *links: Link) -> None:
        self.parts.append(html)
        self.links += links

    def a(self, target: str, anchor: str) -> None:
        self.add(
            f'<a href="{target}">{anchor}</a> ', Link(target, "hyperlink", "a", "href", anchor)
        )

    def link(self, rel: str, target: str, kind: str, extra: str = "") -> None:
        self.add(f'<link rel="{rel}" href="{target}"{extra}>', Link(target, kind, "link", "href"))

    def tag(self, html: str, target: str, kind: str, element: str, attribute: str) -> None:
        self.add(html, Link(target, kind, element, attribute))


@dataclass(frozen=True, kw_only=True)
class SyntheticSite:
    seed: int
    pages: int
    fanout: int = 50
    latency: float = 0.0
    slow_seconds: float = 3.0
    shares: Mapping[Fault, float] = field(default_factory=lambda: dict(DEFAULT_SHARES))

    def __post_init__(self) -> None:
        if self.pages < 1 or self.fanout < 1:
            raise ValueError("a synthetic site needs at least 1 Page and a fanout of at least 1")
        shares = self.shares.values()
        if any(share < 0 for share in shares) or sum(shares) > 1:
            raise ValueError(
                "a synthetic site's fault shares are each 0 or more and add up to 1 at most"
            )

    def fault(self, n: int) -> Fault | None:
        """Only leaves of the spanning tree carry a fault, so none cuts other Pages off."""
        if n * self.fanout + 1 < self.pages or n == 0:
            return None
        draw = next(_stream(self.seed, n, "fault")) / 2**64
        for fault in Fault:
            draw -= self.shares.get(fault, 0.0)
            if draw < 0:
                return fault
        return None

    def children(self, n: int) -> range:
        first = n * self.fanout + 1
        return range(min(first, self.pages), min(first + self.fanout, self.pages))

    def _http_refresh(self, n: int) -> str | None:
        if n % REFRESH_EVERY != 2:
            return None
        return page_path((n + 1) % self.pages)

    def _build(self, n: int, fault: Fault | None) -> _Page:
        page = _Page()
        refs = dict(pool_refs(n))
        numbers = _stream(self.seed, n, "page")
        refresh = self._http_refresh(n)
        if refresh is not None:
            page.links.append(Link(refresh, "http_refresh", "", "Refresh"))
        page.add('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">')
        if fault is Fault.ENDS_WORKER:
            page.add(END_WORKER)
        if n % REFRESH_EVERY == 1:
            target = page_path((n + 1) % self.pages)
            page.tag(
                f'<meta http-equiv="refresh" content="30; url={target}">',
                target,
                "meta_refresh",
                "meta",
                "content",
            )
        topic = WORDS[next(numbers) % len(WORDS)]
        if fault is not Fault.NO_TITLE:
            page.add(f"<title>Page {n} about {topic}</title>")
        page.add(f'<meta name="description" content="All about {topic}, page {n}.">')
        self._head_links(page, n, refs)
        page.add("</head><body><header><nav>")
        for section in range(1, min(NAV_LINKS + 1, self.pages)):
            page.a(page_path(section), f"Section {section}")
        page.add("</nav></header><main>")
        if fault is not Fault.NO_H1:
            page.add(f"<h1>{topic.title()} {n}</h1>")
        self._content(page, n, refs, numbers)
        page.add("</main><footer>")
        for section in range(1, min(FOOTER_REPEATS + 1, self.pages)):
            page.a(page_path(section), f"Section {section}")
        for index in refs[SCRIPTS][4:]:
            url = SCRIPTS.url(index)
            page.tag(f'<script src="{url}"></script>', url, "javascript", "script", "src")
        page.add("</footer></body></html>\n")
        return page

    def _head_links(self, page: _Page, n: int, refs: dict[Pool, tuple[int, ...]]) -> None:
        page.link("canonical", page_path(n), "canonical")
        if n > 0:
            page.link("prev", page_path(n - 1), "pagination")
        if n + 1 < self.pages:
            page.link("next", page_path(n + 1), "pagination")
        for k, language in enumerate(HREFLANGS, start=1):
            target = page_path((n + k * 7_919) % self.pages)
            page.link("alternate", target, "hreflang", f' hreflang="{language}"')
        media = ' media="only screen and (max-width: 640px)"'
        page.link("alternate", MOBILE.url(refs[MOBILE][0]), "mobile_alternate", media)
        page.link("amphtml", AMP.url(refs[AMP][0]), "amphtml")
        for rel, index in zip(MISC_RELS, refs[MISC], strict=True):
            page.link(rel, MISC.url(index), "misc")
        for index in refs[STYLESHEETS]:
            page.link("stylesheet", STYLESHEETS.url(index), "css")
        for index in refs[SCRIPTS][:4]:
            url = SCRIPTS.url(index)
            page.tag(f'<script src="{url}"></script>', url, "javascript", "script", "src")

    def _content(
        self, page: _Page, n: int, refs: dict[Pool, tuple[int, ...]], numbers: Iterator[int]
    ) -> None:
        page.add("<ul>")
        for child in self.children(n):
            page.add("<li>")
            page.a(page_path(child), f"Read page {child}")
            page.add("</li>")
        page.add("</ul><p>")
        for _ in range(RANDOM_LINKS):
            target = next(numbers) % self.pages
            page.a(page_path(target), f"{WORDS[target % len(WORDS)]} {target}")
        page.add("</p>")
        images = [IMAGES.url(index) for index in refs[IMAGES]]
        for url in images[:16]:
            page.tag(f'<img src="{url}" alt="Image">', url, "image", "img", "src")
        page.add(
            f'<picture><source srcset="{images[16]} 1x, {images[17]} 2x">'
            f'<img src="{images[18]}" alt="Picture"></picture>',
            Link(images[16], "image", "source", "srcset"),
            Link(images[17], "image", "source", "srcset"),
            Link(images[18], "image", "img", "src"),
        )
        video = VIDEOS.url(refs[VIDEOS][0])
        page.add(
            f'<video src="{video}" poster="{images[19]}"></video>',
            Link(video, "video", "video", "src"),
            Link(images[19], "image", "video", "poster"),
        )
        audio = AUDIOS.url(refs[AUDIOS][0])
        page.tag(f'<audio src="{audio}"></audio>', audio, "audio", "audio", "src")
        embedded, document = (MEDIA.url(index) for index in refs[MEDIA])
        page.tag(f'<embed src="{embedded}">', embedded, "media", "embed", "src")
        page.tag(f'<object data="{document}"></object>', document, "media", "object", "data")
        frame = page_path((n + 1) % self.pages)
        page.tag(f'<iframe src="{frame}"></iframe>', frame, "iframe", "iframe", "src")
        area = page_path((n + 2) % self.pages)
        page.add(
            f'<map name="m"><area href="{area}" shape="rect" coords="0,0,9,9" alt="Area"></map>',
            Link(area, "hyperlink", "area", "href"),
        )
        page.a(MISSING.url(refs[MISSING][0]), "An old page")
        for index in refs[EXTERNAL]:
            page.a(EXTERNAL.url(index), f"Partner {index}")
        self._pad(page, numbers)

    def _pad(self, page: _Page, numbers: Iterator[int]) -> None:
        footer = FOOTER_REPEATS * 40 + 300
        size = sum(map(len, page.parts)) + footer
        while size < TARGET_SIZE:
            start = next(numbers) % (len(CORPUS) - PARAGRAPH)
            page.add(f"<p>{CORPUS[start : start + PARAGRAPH]}</p>")
            size += PARAGRAPH + 7

    def page_model(self, n: int) -> tuple[Link, ...]:
        """The Links that preparing Page n gives, in document order."""
        fault = self.fault(n)
        return () if fault in LOSES_LINKS else tuple(self._build(n, fault).links)

    def render(self, n: int) -> bytes:
        fault = self.fault(n)
        if fault is Fault.NESTED_DIVS:
            return _nested(n)
        html = "".join(self._build(n, fault).parts)
        if fault is Fault.WRONG_CHARSET:
            # Declared UTF-8 by the Content-Type and the meta, but written in windows-1251.
            return html.replace("</main>", f"<p>{CYRILLIC}</p></main>", 1).encode("cp1251")
        body = html.encode()
        if fault is Fault.INVALID_UTF8:
            body = body.replace(b"</main>", INVALID_BYTES + b"</main>", 1)
        if fault is Fault.MALFORMED_HTML:
            # After every Link, so the broken markup cannot swallow one.
            body = body.replace(b"</body>", MALFORMED + b"</body>", 1)
        return body

    def route(self, path: str) -> Route | None:
        n = page_number(path, self.pages)
        if n is None:
            return _pool_route(path, self.latency)
        fault = self.fault(n)
        if fault is Fault.SERVER_ERROR:
            return Status(500, delay=self.latency)
        delay = self.latency + (self.slow_seconds if fault is Fault.SLOW else 0.0)
        refresh = self._http_refresh(n)
        headers = [] if refresh is None else [("Refresh", f"30; url={refresh}")]
        content_type = "text/html; charset=nonsense" if fault is Fault.UNKNOWN_CHARSET else HTML
        return Bytes(
            self.render(n),
            content_type=content_type,
            headers=headers,
            delay=delay,
            reset_after=RESET_AFTER if fault is Fault.RESET else None,
        )

    def manifest(self) -> dict[str, Any]:
        """The injected counts and the URLs a Crawl must account for, in one pass of hashes."""
        faults = dict.fromkeys(Fault, 0)
        seen = {pool: bytearray(pool.size) for pool in POOLS}
        filled = dict.fromkeys(POOLS, 0)
        open_pools = len(POOLS)
        for n in range(self.pages):
            fault = self.fault(n)
            if fault is not None:
                faults[fault] += 1
            if not open_pools or fault in LOSES_LINKS:
                continue
            for pool, indices in pool_refs(n):
                for index in indices:
                    if not seen[pool][index]:
                        seen[pool][index] = 1
                        filled[pool] += 1
                        open_pools -= filled[pool] == pool.size

        def of_kind(kind: str) -> int:
            return sum(count for pool, count in filled.items() if pool.kind == kind)

        urls = {
            "pages": self.pages,
            "resources": of_kind("resource"),
            "not_followed": of_kind("not_followed"),
            "missing": of_kind("missing"),
            "external": of_kind("external"),
        }
        return {
            "seed": self.seed,
            "pages": self.pages,
            "fanout": self.fanout,
            "latency": self.latency,
            "slow_seconds": self.slow_seconds,
            "shares": {fault.value: self.shares.get(fault, 0.0) for fault in Fault},
            "faults": {fault.value: count for fault, count in faults.items()},
            "outcomes": {fault.value: dict(OUTCOMES[fault]) for fault in Fault},
            "issues": {
                "title-missing": faults[Fault.NO_TITLE],
                "h1-missing": faults[Fault.NO_H1],
                "internal-5xx": faults[Fault.SERVER_ERROR],
                "internal-4xx": filled[MISSING],
            },
            "urls": urls | {"total": sum(urls.values())},
        }

    def as_site(self) -> Site:
        return Site(resolve=self.route)
