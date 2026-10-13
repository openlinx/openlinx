"""The link extractor (020-add-crawl-core D5)."""

from collections.abc import Callable
from typing import Literal
from urllib.parse import urljoin

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import LinkType

type DeclaredIn = Literal["html", "http_header"]

# HTML strips these around a URL attribute; urlsplit strips only the leading ones.
_ASCII_WHITESPACE = "\t\n\x0c\r "


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
    tree = LexborHTMLParser(body.decode("utf-8", "replace"))
    base = _base(tree, url)
    links: list[DiscoveredLink] = []
    for node in tree.css("a[href]"):
        raw = node.attributes.get("href") or ""
        target = _resolved(base, raw)
        if target is None:
            continue
        links.append(
            DiscoveredLink(
                type="hyperlink",
                target=target,
                raw=raw,
                element=node.tag,
                attribute="href",
                rel=(),
                nofollow=False,
                declared_in="html",
                ordinal=len(links) + 1,
                is_internal=is_internal(target),
            )
        )
    return links


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
