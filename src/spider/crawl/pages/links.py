"""The link extractor (020-add-crawl-core D5)."""

import re
from collections.abc import Callable, Iterator, Mapping

from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.following import skip_reason
from spider.crawl.pages.decoding import decode_html, query_codec
from spider.crawl.pages.refresh import refresh_url
from spider.crawl.references import C0_OR_SPACE, DiscoveredLink, resolve_base, resolve_reference
from spider.crawl.urls import NormalizedUrl
from spider.store.records import DeclaredIn, LinkType

type _Reference = tuple[LinkType, str, str]

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
# The elements a <noscript>'s text gives Links of: its <link> and <meta> are head metadata,
# which a browser that runs scripts never sees.
_NOSCRIPT_ELEMENTS = ", ".join(
    [
        *(f"{tag}[{attribute}]" for tag, (_, attribute) in _SINGLE_REFERENCES.items()),
        "img, video, source, track",
    ]
)
# Only a foreign <noscript> has elements in the tree.
_ELEMENTS = (
    f"{_NOSCRIPT_ELEMENTS}, link[href]:not(noscript link), meta[http-equiv]:not(noscript meta),"
    " noscript"
)
_FOREIGN_ROOTS = frozenset({"svg", "math"})
# HTML integration points (HTML Standard): inside one a <noscript> is HTML, as in the body.
_INTEGRATION_POINTS = frozenset({"foreignObject", "desc", "title", "mi", "mo", "mn", "ms", "mtext"})
_HTML_ENCODINGS = frozenset({"text/html", "application/xhtml+xml"})
_MEDIA_TYPES: Mapping[str, LinkType] = {"video": "video", "audio": "audio"}
PAGINATION_RELS = frozenset({"next", "prev", "previous"})
# These name an origin to connect to, not a file.
_ORIGIN_HINTS = frozenset({"preconnect", "dns-prefetch"})
# The srcset grammar of HTML: a URL ends at white space, or at the commas closing it, which
# then end the candidate; otherwise its descriptors run to the next comma outside parentheses.
_SRCSET_CANDIDATE = re.compile(
    r"[\t\n\x0c\r ,]*([^\t\n\x0c\r ]*)(?:(?<!,)(?:[^,(]|\([^)]*\)?)*,?)?"
)


def extract_links(
    body: bytes,
    content_type: str | None,
    url: NormalizedUrl,
    *,
    is_internal: Callable[[NormalizedUrl], bool],
    strip_params: re.Pattern[str] | None,
    page_nofollow: bool = False,
    follow_nofollow: bool = False,
) -> list[DiscoveredLink]:
    decoded = decode_html(body, content_type)
    tree = parse_html(decoded.text)
    return links_in_tree(
        tree,
        base=base_url(tree, url, decoded.encoding),
        encoding=decoded.encoding,
        is_internal=is_internal,
        strip_params=strip_params,
        page_nofollow=page_nofollow,
        follow_nofollow=follow_nofollow,
    )


def parse_html(text: str) -> LexborHTMLParser:
    """As a browser that runs scripts parses it (design D5)."""
    return LexborHTMLParser(text, scripting=True)


def rel_tokens(rel: str) -> tuple[str, ...]:
    """HTML and RFC 8288 compare them without ASCII case."""
    return tuple(_ASCII_TOKEN.findall(rel.lower()))


def base_url(tree: LexborHTMLParser, url: NormalizedUrl, encoding: str) -> str:
    """What the Page's references resolve against: its base href, else the response URL."""
    return _base(tree, url, query_codec(encoding))


def links_in_tree(
    tree: LexborHTMLParser,
    *,
    base: str,
    encoding: str,
    is_internal: Callable[[NormalizedUrl], bool],
    strip_params: re.Pattern[str] | None,
    page_nofollow: bool,
    follow_nofollow: bool,
    first_ordinal: int = 1,
) -> list[DiscoveredLink]:
    """The Links of a parsed document, for page preparation, which parses once (design D9)."""
    codec = query_codec(encoding)
    links: list[DiscoveredLink] = []
    for node, declared_in in _link_nodes(tree):
        attributes = node.attributes
        rel = rel_tokens(attributes.get("rel") or "")
        for link_type, attribute, raw in _references(node.tag or "", attributes, rel, node.parent):
            target = resolve_reference(base, raw, codec, strip_params)
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
                    skip_reason=skip_reason(
                        link_type,
                        "nofollow" in rel,
                        page_nofollow=page_nofollow,
                        follow_nofollow=follow_nofollow,
                    ),
                    declared_in=declared_in,
                    ordinal=first_ordinal + len(links),
                    is_internal=is_internal(target),
                )
            )
    return links


def _link_nodes(tree: LexborHTMLParser) -> Iterator[tuple[LexborNode, DeclaredIn]]:
    # A foreign <noscript>'s text is decoded markup, and its child elements are in the tree.
    foreign = {node.mem_id for node in tree.css("svg noscript, math noscript") if _is_foreign(node)}
    # Where the parser placed the element: what it moved out of <head> is in <body>.
    head = tree.head
    in_head = set() if head is None else {node.mem_id for node in head.css(_ELEMENTS)}
    for node in tree.css(_ELEMENTS):
        declared_in: DeclaredIn = "head" if node.mem_id in in_head else "body"
        if node.tag != "noscript":
            yield node, declared_in
        elif node.mem_id not in foreign:
            # Its fragment's Links take the <noscript>'s place.
            for found in _noscript_links(node.text()):
                yield found, declared_in


def _is_foreign(noscript: LexborNode) -> bool:
    node = noscript.parent
    while node is not None and node.tag not in _FOREIGN_ROOTS:
        if node.tag in _INTEGRATION_POINTS or (
            node.tag == "annotation-xml"
            and (node.attributes.get("encoding") or "").lower() in _HTML_ENCODINGS
        ):
            return False
        node = node.parent
    return node is not None


def _noscript_links(text: str) -> Iterator[LexborNode]:
    if text:
        fragment = LexborHTMLParser(text, is_fragment=True)
        yield from fragment.css(_NOSCRIPT_ELEMENTS)


def _references(
    tag: str,
    attributes: Mapping[str, str | None],
    rel: tuple[str, ...],
    parent: LexborNode | None,
) -> Iterator[_Reference]:
    match tag:
        case "meta":
            if (attributes.get("http-equiv") or "").lower() == "refresh":
                raw = refresh_url(attributes.get("content") or "")
                if raw is not None:
                    yield "meta_refresh", "content", raw
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
    if "canonical" in rel:
        return "canonical"
    if "stylesheet" in rel:
        return "css"
    if "amphtml" in rel:
        return "amphtml"
    if not PAGINATION_RELS.isdisjoint(rel):
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
    if raw is not None and (link_type == "hyperlink" or raw.strip(C0_OR_SPACE)):
        yield link_type, attribute, raw


def _srcset(attributes: Mapping[str, str | None]) -> Iterator[_Reference]:
    for candidate in _SRCSET_CANDIDATE.finditer(attributes.get("srcset") or ""):
        url = candidate[1].rstrip(",")
        if url:
            yield "image", "srcset", url


def _base(tree: LexborHTMLParser, url: NormalizedUrl, codec: str | None) -> str:
    node = tree.css_first("base[href]")
    if node is None:
        return url
    return resolve_base(url, node.attributes.get("href") or "", codec)
