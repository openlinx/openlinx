"""The link extractor (020-add-crawl-core D5)."""

import re
from collections.abc import Callable, Container, Iterable, Iterator, Mapping
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.following import skip_reason
from spider.crawl.pages.decoding import query_codec
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
_PAGINATION_RELS = frozenset({"next", "prev", "previous"})
# A <link>'s or a Link header's type by its rel tokens and attributes, the first that matches.
_REL_TYPES: tuple[tuple[LinkType, Callable[[tuple[str, ...], Container[str]], bool]], ...] = (
    ("canonical", lambda rel, attributes: "canonical" in rel),
    ("css", lambda rel, attributes: "stylesheet" in rel),
    ("amphtml", lambda rel, attributes: "amphtml" in rel),
    ("pagination", lambda rel, attributes: not _PAGINATION_RELS.isdisjoint(rel)),
    ("hreflang", lambda rel, attributes: "alternate" in rel and "hreflang" in attributes),
    ("mobile_alternate", lambda rel, attributes: "alternate" in rel and "media" in attributes),
)
_ALL_REL_TYPES = frozenset(link_type for link_type, _ in _REL_TYPES)
# These name an origin to connect to, not a file.
_ORIGIN_HINTS = frozenset({"preconnect", "dns-prefetch"})
# The srcset grammar of HTML: a URL ends at white space, or at the commas closing it, which
# then end the candidate; otherwise its descriptors run to the next comma outside parentheses.
_SRCSET_CANDIDATE = re.compile(
    r"[\t\n\x0c\r ,]*([^\t\n\x0c\r ]*)(?:(?<!,)(?:[^,(]|\([^)]*\)?)*,?)?"
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


def discovered_link(
    link_type: LinkType,
    target: NormalizedUrl,
    raw: str,
    *,
    element: str | None,
    attribute: str | None,
    rel: tuple[str, ...],
    declared_in: DeclaredIn,
    ordinal: int,
    is_internal: bool,
    page_nofollow: bool,
    follow_nofollow: bool,
) -> DiscoveredLink:
    """A Link of the document or of a header: its nofollow is its rel's, and the follow rule
    gives its skip reason (design D5)."""
    nofollow = "nofollow" in rel
    return DiscoveredLink(
        type=link_type,
        target=target,
        raw=raw,
        element=element,
        attribute=attribute,
        rel=rel,
        nofollow=nofollow,
        skip_reason=skip_reason(
            link_type, nofollow, page_nofollow=page_nofollow, follow_nofollow=follow_nofollow
        ),
        declared_in=declared_in,
        ordinal=ordinal,
        is_internal=is_internal,
    )


def rel_link_type(
    rel: tuple[str, ...], attributes: Container[str], types: Container[LinkType]
) -> LinkType | None:
    """The first of `types` that the rel tokens and the attributes match (_REL_TYPES)."""
    return next(
        (
            link_type
            for link_type, matches in _REL_TYPES
            if link_type in types and matches(rel, attributes)
        ),
        None,
    )


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
    for reference in link_references(tree):
        target = resolve_reference(base, reference.raw, codec, strip_params)
        if target is None:
            continue
        links.append(
            discovered_link(
                reference.type,
                target,
                reference.raw,
                element=reference.element.tag,
                attribute=reference.attribute,
                rel=reference.rel,
                declared_in=reference.declared_in,
                ordinal=first_ordinal + len(links),
                is_internal=is_internal(target),
                page_nofollow=page_nofollow,
                follow_nofollow=follow_nofollow,
            )
        )
    return links


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkReference:
    """A reference of a document before it is resolved, with the element it came from and
    the element of the document that places it: the element itself, or the <noscript> whose
    text held it."""

    element: LexborNode
    placing: LexborNode
    declared_in: DeclaredIn
    type: LinkType
    attribute: str
    raw: str
    rel: tuple[str, ...]


def link_references(tree: LexborHTMLParser) -> Iterator[LinkReference]:
    """In the order that links_in_tree numbers the Links it resolves from them."""
    for node, placing, declared_in in _link_nodes(tree):
        attributes = node.attributes
        rel = rel_tokens(attributes.get("rel") or "")
        for link_type, attribute, raw in _references(node.tag or "", attributes, rel, node.parent):
            yield LinkReference(
                element=node,
                placing=placing,
                declared_in=declared_in,
                type=link_type,
                attribute=attribute,
                raw=raw,
                rel=rel,
            )


def locate_links(
    tree: LexborHTMLParser, links: Iterable[DiscoveredLink]
) -> list[tuple[DiscoveredLink, LexborNode, LexborNode]]:
    """Each HTML Link that links_in_tree found in the tree, with the element it came from and
    the element that places it; header Links are left out. Raises RuntimeError for a Link the
    tree does not hold."""
    pending = [link for link in links if link.declared_in != "http_header"]
    located: list[tuple[DiscoveredLink, LexborNode, LexborNode]] = []
    # Resolution reads only a reference and the document's base and encoding, so a reference
    # that matches the next Link is the one that gave it, and one that does not resolved to
    # nothing.
    for reference in link_references(tree):
        if len(located) == len(pending):
            break
        link = pending[len(located)]
        if (link.element, link.attribute, link.type, link.raw) == (
            reference.element.tag,
            reference.attribute,
            reference.type,
            reference.raw,
        ):
            located.append((link, reference.element, reference.placing))
    if len(located) != len(pending):
        raise RuntimeError(f"link {pending[len(located)].ordinal} is not in the tree")
    return located


def _link_nodes(tree: LexborHTMLParser) -> Iterator[tuple[LexborNode, LexborNode, DeclaredIn]]:
    # A foreign <noscript>'s text is decoded markup, and its child elements are in the tree.
    foreign = {node.mem_id for node in tree.css("svg noscript, math noscript") if _is_foreign(node)}
    # Where the parser placed the element: what it moved out of <head> is in <body>.
    head = tree.head
    in_head = set() if head is None else {node.mem_id for node in head.css(_ELEMENTS)}
    for node in tree.css(_ELEMENTS):
        declared_in: DeclaredIn = "head" if node.mem_id in in_head else "body"
        if node.tag != "noscript":
            yield node, node, declared_in
        elif node.mem_id not in foreign:
            # Its fragment's Links take the <noscript>'s place.
            for found in _noscript_links(node.text()):
                yield found, node, declared_in


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
    link_type = rel_link_type(rel, attributes, _ALL_REL_TYPES)
    if link_type is not None:
        return link_type
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
