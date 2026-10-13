"""The link extractor (020-add-crawl-core D5)."""

import re
from collections.abc import Callable, Iterator, Mapping
from typing import Literal
from urllib.parse import urljoin

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.decoding import decode_html
from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import LinkType

type DeclaredIn = Literal["html", "http_header"]
type _Reference = tuple[LinkType, str, str]

# HTML strips these around a URL attribute; urlsplit strips only the leading ones.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_ASCII_TOKEN = re.compile(r"[^\t\n\x0c\r ]+")
_ELEMENTS = (
    "a[href], area[href], link[href], img, video, audio, source, track, iframe[src], frame[src],"
    " script[src], embed[src], object[data]"
)
_SOURCES: Mapping[str, tuple[LinkType, str]] = {
    "iframe": ("iframe", "src"),
    "frame": ("iframe", "src"),
    "script": ("javascript", "src"),
    "embed": ("media", "src"),
    "object": ("media", "data"),
}
_MEDIA_TYPES: Mapping[str, LinkType] = {"video": "video", "audio": "audio"}
_PAGINATION = frozenset({"next", "prev", "previous"})
# These name an origin to connect to, not a file.
_ORIGIN_HINTS = frozenset({"preconnect", "dns-prefetch"})
# The srcset grammar of HTML: a URL ends at white space, or at the commas closing it, which
# then end the candidate; otherwise its descriptors run to the next comma outside parentheses.
_SRCSET_CANDIDATE = re.compile(
    r"[\t\n\x0c\r ,]*([^\t\n\x0c\r ]*)(?:(?<!,)(?:[^,(]|\([^)]*\)?)*,?)?"
)


class DiscoveredLink(msgspec.Struct, frozen=True, kw_only=True):
    type: LinkType
    target: NormalizedUrl
    raw: str
    element: str | None
    attribute: str | None
    rel: tuple[str, ...]
    nofollow: bool
    declared_in: DeclaredIn
    ordinal: int
    is_internal: bool


def extract_links(
    body: bytes,
    content_type: str | None,
    url: NormalizedUrl,
    *,
    is_internal: Callable[[NormalizedUrl], bool],
) -> list[DiscoveredLink]:
    tree = LexborHTMLParser(decode_html(body, content_type).text)
    base = _base(tree, url)
    links: list[DiscoveredLink] = []
    for node in tree.css(_ELEMENTS):
        attributes = node.attributes
        rel = tuple(_ASCII_TOKEN.findall((attributes.get("rel") or "").lower()))
        for link_type, attribute, raw in _references(node.tag, attributes, rel, node.parent):
            target = _resolved(base, raw)
            if target is None:
                continue
            links.append(
                DiscoveredLink(
                    type=link_type,
                    target=target,
                    raw=raw,
                    element=node.tag,
                    attribute=attribute,
                    rel=rel,
                    nofollow="nofollow" in rel,
                    declared_in="html",
                    ordinal=len(links) + 1,
                    is_internal=is_internal(target),
                )
            )
    return links


def _references(
    tag: str | None,
    attributes: Mapping[str, str | None],
    rel: tuple[str, ...],
    parent: LexborNode | None,
) -> Iterator[_Reference]:
    match tag:
        case "a" | "area":
            yield from _attribute("hyperlink", "href", attributes)
        case "link":
            link_type = _link_type(rel, attributes)
            if link_type is not None:
                yield from _attribute(link_type, "href", attributes)
        case "img":
            yield from _attribute("image", "src", attributes)
            yield from _srcset(attributes)
        case "video":
            yield from _attribute("video", "src", attributes)
            yield from _attribute("image", "poster", attributes)
        case "audio":
            yield from _attribute("audio", "src", attributes)
        case "iframe" | "frame" | "script" | "embed" | "object":
            yield from _attribute(*_SOURCES[tag], attributes)
        case "source" | "track":
            media_type = _MEDIA_TYPES.get(parent.tag or "") if parent is not None else None
            if media_type is not None:
                yield from _attribute(media_type, "src", attributes)
            yield from _srcset(attributes)


def _link_type(rel: tuple[str, ...], attributes: Mapping[str, str | None]) -> LinkType | None:
    if "stylesheet" in rel:
        return "css"
    if not _PAGINATION.isdisjoint(rel):
        return "pagination"
    if "alternate" in rel and "hreflang" in attributes:
        return "hreflang"
    if "alternate" in rel and "media" in attributes:
        return "mobile_alternate"
    if rel and _ORIGIN_HINTS.issuperset(rel):
        return None
    return "misc"


def _attribute(
    link_type: LinkType, attribute: str, attributes: Mapping[str, str | None]
) -> Iterator[_Reference]:
    raw = attributes.get(attribute)
    if raw is not None:
        yield link_type, attribute, raw


def _srcset(attributes: Mapping[str, str | None]) -> Iterator[_Reference]:
    for candidate in _SRCSET_CANDIDATE.finditer(attributes.get("srcset") or ""):
        url = candidate[1].rstrip(",")
        if url:
            yield "image", "srcset", url


def _base(tree: LexborHTMLParser, url: NormalizedUrl) -> str:
    node = tree.css_first("base[href]")
    if node is None:
        return url
    return _resolved(url, node.attributes.get("href") or "") or url


def _resolved(base: str, raw: str) -> NormalizedUrl | None:
    try:
        joined = urljoin(base, raw.strip(_ASCII_WHITESPACE))
    except ValueError:
        return None
    target = normalize_url(joined)
    return target if isinstance(target, str) else None
