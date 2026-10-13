"""A seeded synthetic site of up to 500,000 Pages, computed per request (026-add-parse-pool D6)."""

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple

from tests.fixture_site.routes import Bytes, Route, Site

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


NO_FAULTS: Mapping[Fault, float] = {}


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

    def url(self, index: int) -> str:
        return self.path.format(index)


IMAGES = Pool("images", 1_500, "/r/i/{}.jpg", "image/jpeg")
STYLESHEETS = Pool("stylesheets", TEMPLATES * 8, "/r/c/{}.css", "text/css")
SCRIPTS = Pool("scripts", TEMPLATES * 10, "/r/j/{}.js", "text/javascript")
VIDEOS = Pool("videos", 100, "/r/v/{}.mp4", "video/mp4")
AUDIOS = Pool("audios", 100, "/r/a/{}.mp3", "audio/mpeg")
MEDIA = Pool("media", 100, "/r/m/{}.pdf", "application/pdf")
AMP = Pool("amp", 100, "/amp/{}", HTML)
MOBILE = Pool("mobile", 100, "/m/{}", HTML)
MISC = Pool("misc", 3, "/misc/{}", "application/octet-stream")
MISSING = Pool("missing", 100, "/missing/{}", HTML)
POOLS = (IMAGES, STYLESHEETS, SCRIPTS, VIDEOS, AUDIOS, MEDIA, AMP, MOBILE, MISC, MISSING)
SERVED_POOLS = tuple(pool for pool in POOLS if pool is not MISSING)
MISC_RELS = ("icon", "manifest", "alternate")


def page_path(n: int) -> str:
    return "/" if n == 0 else f"/p/{n}"


def _page_number(path: str, pages: int) -> int | None:
    if path == "/":
        return 0
    return _number(path.removeprefix("/p/"), pages) if path.startswith("/p/") else None


def _number(digits: str, below: int) -> int | None:
    if not digits.isdigit() or str(int(digits)) != digits:
        return None
    n = int(digits)
    return n if n < below else None


def _pool_route(path: str) -> Route | None:
    for pool in SERVED_POOLS:
        prefix, _, suffix = pool.path.partition("{}")
        if path.startswith(prefix) and path.endswith(suffix):
            index = _number(path[len(prefix) : len(path) - len(suffix)], pool.size)
            if index is not None:
                return Bytes(f"{pool.name} {index}".encode(), content_type=pool.content_type)
    return None


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
    shares: Mapping[Fault, float] = field(default_factory=dict)

    def children(self, n: int) -> range:
        first = n * self.fanout + 1
        return range(min(first, self.pages), min(first + self.fanout, self.pages))

    def _http_refresh(self, n: int) -> str | None:
        if n % REFRESH_EVERY != 2:
            return None
        return page_path((n + 1) % self.pages)

    def _build(self, n: int) -> _Page:
        page = _Page()
        refs = dict(pool_refs(n))
        numbers = _stream(self.seed, n, "page")
        refresh = self._http_refresh(n)
        if refresh is not None:
            page.links.append(Link(refresh, "http_refresh", "", "Refresh"))
        page.add('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">')
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
        page.add(f"<title>Page {n} about {topic}</title>")
        page.add(f'<meta name="description" content="All about {topic}, page {n}.">')
        self._head_links(page, n, refs)
        page.add("</head><body><header><nav>")
        for section in range(1, min(NAV_LINKS + 1, self.pages)):
            page.a(page_path(section), f"Section {section}")
        page.add(f"</nav></header><main><h1>{topic.title()} {n}</h1>")
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
        self._pad(page, numbers)

    def _pad(self, page: _Page, numbers: Iterator[int]) -> None:
        footer = FOOTER_REPEATS * 40 + 300
        size = sum(map(len, page.parts)) + footer
        while size < TARGET_SIZE:
            start = next(numbers) % (len(CORPUS) - PARAGRAPH)
            page.add(f"<p>{CORPUS[start : start + PARAGRAPH]}</p>")
            size += PARAGRAPH + 7

    def page_model(self, n: int) -> tuple[Link, ...]:
        return tuple(self._build(n).links)

    def render(self, n: int) -> bytes:
        return "".join(self._build(n).parts).encode()

    def route(self, path: str) -> Route | None:
        n = _page_number(path, self.pages)
        if n is None:
            return _pool_route(path)
        refresh = self._http_refresh(n)
        headers = [] if refresh is None else [("Refresh", f"30; url={refresh}")]
        return Bytes(self.render(n), content_type=HTML, headers=headers)

    def as_site(self) -> Site:
        return Site(resolve=self.route)
