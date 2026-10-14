"""The Links of the HTTP Link and Refresh headers (020-add-crawl-core D5; RFC 8288)."""

import re
from collections.abc import Callable, Iterable, Iterator, Mapping

from spider.crawl.links import PAGINATION_RELS, DiscoveredLink, rel_tokens, resolve_reference
from spider.crawl.refresh import refresh_url
from spider.crawl.urls import NormalizedUrl
from spider.store.records import LinkType

# A link-value of RFC 8288: a target in angle brackets, then its parameters, each a name
# with an optional token or quoted string; a comma outside them ends the value.
_LINK_VALUE = re.compile(
    r'<([^>]*)>((?:[\t ]*;[\t ]*[^;,=\t ]+[\t ]*(?:=[\t ]*(?:"(?:[^"\\]|\\.)*"|[^;,]*))?)*)'
)
_LINK_PARAM = re.compile(r';[\t ]*([^;,=\t ]+)[\t ]*(?:=[\t ]*("(?:[^"\\]|\\.)*"|[^;,]*))?')
_QUOTED_PAIR = re.compile(r"\\(.)")


def header_links(
    headers: Iterable[tuple[str, str]],
    url: NormalizedUrl,
    *,
    is_internal: Callable[[NormalizedUrl], bool],
) -> list[DiscoveredLink]:
    """The Links of the `Link` and `Refresh` headers, in the order received (design D5)."""
    links: list[DiscoveredLink] = []
    for name, value in headers:
        for link_type, raw, rel in _header_references(name.lower(), value):
            # Against the response URL: a header knows no base href.
            target = resolve_reference(url, raw, None)
            if target is None:
                continue
            links.append(
                DiscoveredLink(
                    type=link_type,
                    target=target,
                    raw=raw,
                    element=None,
                    attribute=None,
                    rel=rel,
                    nofollow="nofollow" in rel,
                    declared_in="http_header",
                    ordinal=len(links) + 1,
                    is_internal=is_internal(target),
                )
            )
    return links


def _header_references(name: str, value: str) -> Iterator[tuple[LinkType, str, tuple[str, ...]]]:
    if name == "refresh":
        raw = refresh_url(value)
        if raw is not None:
            yield "http_refresh", raw, ()
    elif name == "link":
        for link_value in _LINK_VALUE.finditer(value):
            params: dict[str, str] = {}
            for param in _LINK_PARAM.finditer(link_value[2]):
                # RFC 8288: a parameter after the first of its name is ignored.
                params.setdefault(param[1].lower(), _unquoted(param[2] or ""))
            rel = rel_tokens(params.get("rel", ""))
            link_type = _header_link_type(rel, params)
            if link_type is not None:
                yield link_type, link_value[1], rel


def _header_link_type(rel: tuple[str, ...], params: Mapping[str, str]) -> LinkType | None:
    if "canonical" in rel:
        return "canonical"
    if not PAGINATION_RELS.isdisjoint(rel):
        return "pagination"
    if "alternate" in rel and "hreflang" in params:
        return "hreflang"
    return None


def _unquoted(value: str) -> str:
    value = value.strip("\t ")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return _QUOTED_PAIR.sub(r"\1", value[1:-1])
    return value
