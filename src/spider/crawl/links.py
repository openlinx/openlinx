"""The link extractor (020-add-crawl-core D5)."""

import re
from collections.abc import Callable, Iterator, Mapping
from urllib.parse import urljoin

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.decoding import decode_html, query_codec
from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import DeclaredIn, LinkType

type _Reference = tuple[LinkType, str, str]

# The URL Standard strips these around a reference and removes tabs and newlines inside it;
# urlsplit strips only the leading ones.
_C0_OR_SPACE = "".join(map(chr, range(0x21)))
_TAB_OR_NEWLINE = str.maketrans("", "", "\t\n\r")
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
_HTTP_SCHEMES = frozenset({"http", "https"})
# In http and https URLs browsers read a backslash as a slash, before the query.
_SLASHES = "/\\"
_QUERY_OR_FRAGMENT = re.compile(r"[?#]")
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
    decoded = decode_html(body, content_type)
    tree = LexborHTMLParser(decoded.text)
    base = base_url(tree, url, decoded.encoding)
    return links_in_tree(tree, base=base, encoding=decoded.encoding, is_internal=is_internal)


def base_url(tree: LexborHTMLParser, url: NormalizedUrl, encoding: str) -> str:
    """What the Page's references resolve against: its base href, else the response URL."""
    return _base(tree, url, query_codec(encoding))


def links_in_tree(
    tree: LexborHTMLParser,
    *,
    base: str,
    encoding: str,
    is_internal: Callable[[NormalizedUrl], bool],
) -> list[DiscoveredLink]:
    """The Links of a parsed document, for page preparation, which parses once (design D9)."""
    codec = query_codec(encoding)
    links: list[DiscoveredLink] = []
    for node in tree.css(_ELEMENTS):
        attributes = node.attributes
        rel = tuple(_ASCII_TOKEN.findall((attributes.get("rel") or "").lower()))
        for link_type, attribute, raw in _references(node.tag or "", attributes, rel, node.parent):
            target = _resolved(base, raw, codec)
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
    if raw is not None and (link_type == "hyperlink" or raw.strip(_C0_OR_SPACE)):
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
    href = _cleaned(node.attributes.get("href") or "")
    scheme = _SCHEME.match(href)
    # Unnormalised, as browsers resolve against it: a javascript: base resolves nothing.
    if scheme is not None and scheme[1].lower() not in _HTTP_SCHEMES:
        return href
    return _joined(url, href, codec) or url


def _resolved(base: str, raw: str, codec: str | None) -> NormalizedUrl | None:
    joined = _joined(base, _cleaned(raw), codec)
    if joined is None:
        return None
    target = normalize_url(joined)
    return target if isinstance(target, str) else None


def _cleaned(raw: str) -> str:
    return raw.strip(_C0_OR_SPACE).translate(_TAB_OR_NEWLINE)


def _joined(base: str, reference: str, codec: str | None) -> str | None:
    """The http or https URL a browser makes of the reference, or None (URL Standard)."""
    base_scheme = base.partition(":")[0]
    match = _SCHEME.match(reference)
    if match is not None:
        scheme = match[1].lower()
        if scheme not in _HTTP_SCHEMES:
            return None
        # The base's own scheme makes a relative reference; the other one names a host.
        if scheme != base_scheme:
            return _with_host(scheme, reference[match.end() :], codec)
        reference = reference[match.end() :]
    if base_scheme not in _HTTP_SCHEMES:
        return None
    if reference[0:1] in ("/", "\\") and reference[1:2] in ("/", "\\"):
        return _with_host(base_scheme, reference, codec)
    try:
        joined = urljoin(base, _forward_slashes(reference))
    except ValueError:
        return None
    return _query_encoded(joined, codec)


def _with_host(scheme: str, rest: str, codec: str | None) -> str | None:
    rest = _forward_slashes(rest.lstrip(_SLASHES))
    if rest[:1] in ("", "/", "?", "#"):
        return None
    return _query_encoded(f"{scheme}://{rest}", codec)


def _forward_slashes(reference: str) -> str:
    if "\\" not in reference:
        return reference
    end = _QUERY_OR_FRAGMENT.search(reference)
    split = end.start() if end is not None else len(reference)
    return reference[:split].replace("\\", "/") + reference[split:]


def _query_encoded(url: str, codec: str | None) -> str:
    if codec is None or url.isascii():
        return url
    url, hash_mark, fragment = url.partition("#")
    head, question_mark, query = url.partition("?")
    if query.isascii():
        return f"{url}{hash_mark}{fragment}"
    data = query.encode(codec, "xmlcharrefreplace")
    # The "#" of a character reference would otherwise end the query.
    encoded = "".join(chr(b) if b < 0x80 else f"%{b:02X}" for b in data).replace("#", "%23")
    return f"{head}{question_mark}{encoded}{hash_mark}{fragment}"
