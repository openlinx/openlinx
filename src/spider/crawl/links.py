"""The link extractor (020-add-crawl-core D5)."""

import re
from collections.abc import Callable, Iterator, Mapping
from urllib.parse import urljoin, urlsplit

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.decoding import decode_html
from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import DeclaredIn, LinkType

type _Reference = tuple[LinkType, str, str]

# HTML strips these around a URL attribute; urlsplit strips only the leading ones.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_ASCII_TOKEN = re.compile(r"[^\t\n\x0c\r ]+")
# Elements with one URL attribute; link, img, video, source and track have rules of their own.
_SINGLE_REFERENCES: Mapping[str, tuple[LinkType, str]] = {
    "a": ("hyperlink", "href"),
    "area": ("hyperlink", "href"),
    "audio": ("audio", "src"),
    "iframe": ("iframe", "src"),
    "frame": ("iframe", "src"),
    "script": ("javascript", "src"),
    "embed": ("media", "src"),
    "object": ("media", "data"),
}
_ELEMENTS = ", ".join(
    [
        *(f"{tag}[{attribute}]" for tag, (_, attribute) in _SINGLE_REFERENCES.items()),
        "link[href], img, video, source, track",
    ]
)
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
        for link_type, attribute, raw in _references(node.tag or "", attributes, rel, node.parent):
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
    tag: str,
    attributes: Mapping[str, str | None],
    rel: tuple[str, ...],
    parent: LexborNode | None,
) -> Iterator[_Reference]:
    match tag:
        case "link":
            link_type = _link_type(rel, attributes)
            if link_type is not None:
                yield from _from_attribute(link_type, "href", attributes)
        case "img":
            yield from _from_attribute("image", "src", attributes)
            yield from _srcset(attributes)
        case "video":
            yield from _from_attribute("video", "src", attributes)
            yield from _from_attribute("image", "poster", attributes)
        case "source" | "track":
            media_type = _MEDIA_TYPES.get(parent.tag or "") if parent is not None else None
            if media_type is not None:
                yield from _from_attribute(media_type, "src", attributes)
            if tag == "source":
                yield from _srcset(attributes)
        case _:
            yield from _from_attribute(*_SINGLE_REFERENCES[tag], attributes)


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


def _from_attribute(
    link_type: LinkType, attribute: str, attributes: Mapping[str, str | None]
) -> Iterator[_Reference]:
    raw = attributes.get(attribute)
    # An empty href links to the Page itself; an empty src, data or poster names no file.
    if raw is not None and (link_type == "hyperlink" or raw.strip(_ASCII_WHITESPACE)):
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
    # Unnormalised, as browsers resolve against it: a javascript: base resolves nothing.
    try:
        return urljoin(url, (node.attributes.get("href") or "").strip(_ASCII_WHITESPACE))
    except ValueError:
        return url


def _resolved(base: str, raw: str) -> NormalizedUrl | None:
    reference = raw.strip(_ASCII_WHITESPACE)
    try:
        parts = urlsplit(reference)
        joined = urljoin(base, reference)
    except ValueError:
        return None
    # urljoin reads an empty authority ("//", "http:///x") as a path; it names no host.
    after_scheme = reference[len(parts.scheme) + 1 :] if parts.scheme else reference
    if after_scheme.startswith("//") and not parts.netloc:
        return None
    target = normalize_url(joined)
    return target if isinstance(target, str) else None
