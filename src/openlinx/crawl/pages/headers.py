"""The Links of the HTTP Link and Refresh headers (020-add-crawl-core D5; RFC 8288)."""

import re
from collections.abc import Callable, Iterable, Iterator, Mapping

from openlinx.crawl.pages.links import discovered_link, rel_link_type, rel_tokens
from openlinx.crawl.pages.refresh import refresh_url
from openlinx.crawl.references import DiscoveredLink, resolve_reference
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import LinkType

# A link-value of RFC 8288: a target in angle brackets, then its parameters, each a name
# with an optional token or quoted string; a comma outside them ends the value.
_LINK_VALUE = re.compile(
    r'<([^>]*)>((?:[\t ]*;[\t ]*[^;,=\t ]+[\t ]*(?:=[\t ]*(?:"(?:[^"\\]|\\.)*"|[^;,]*))?)*)'
)
_LINK_PARAM = re.compile(r';[\t ]*([^;,=\t ]+)[\t ]*(?:=[\t ]*("(?:[^"\\]|\\.)*"|[^;,]*))?')
_QUOTED_PAIR = re.compile(r"\\(.)")
# The Link types a Link header gives; any other rel gives no Link.
_HEADER_TYPES: frozenset[LinkType] = frozenset({"canonical", "pagination", "hreflang"})


def header_links(
    headers: Iterable[tuple[str, str]],
    url: NormalizedUrl,
    *,
    is_internal: Callable[[NormalizedUrl], bool],
    strip_params: re.Pattern[str] | None,
) -> list[DiscoveredLink]:
    """In the order received, numbered from 1: they come before the document's (design D5)."""
    return [
        link
        for link, _ in header_links_with_parameters(
            headers, url, is_internal=is_internal, strip_params=strip_params
        )
    ]


def header_links_with_parameters(
    headers: Iterable[tuple[str, str]],
    url: NormalizedUrl,
    *,
    is_internal: Callable[[NormalizedUrl], bool],
    strip_params: re.Pattern[str] | None,
) -> Iterator[tuple[DiscoveredLink, Mapping[str, str]]]:
    """Each header Link with the parameters of its link-value, by lower-cased name; a Refresh
    Link has none."""
    ordinal = 1
    for name, value in headers:
        for link_type, raw, rel, parameters in _header_references(name.lower(), value):
            # Against the response URL: a header knows no base href.
            target = resolve_reference(url, raw, None, strip_params)
            if target is None:
                continue
            link = discovered_link(
                link_type,
                target,
                raw,
                element=None,
                attribute=None,
                rel=rel,
                declared_in="http_header",
                ordinal=ordinal,
                is_internal=is_internal(target),
                # A header gives no hyperlink, the one type nofollow applies to.
                page_nofollow=False,
                follow_nofollow=False,
            )
            ordinal += 1
            yield link, parameters


def _header_references(
    name: str, value: str
) -> Iterator[tuple[LinkType, str, tuple[str, ...], Mapping[str, str]]]:
    if name == "refresh":
        raw = refresh_url(value)
        if raw is not None:
            yield "http_refresh", raw, (), {}
    elif name == "link":
        for link_value in _LINK_VALUE.finditer(value):
            params: dict[str, str] = {}
            for param in _LINK_PARAM.finditer(link_value[2]):
                # RFC 8288: a parameter after the first of its name is ignored.
                params.setdefault(param[1].lower(), _unquoted(param[2] or ""))
            # RFC 8288: an anchor makes the link-value describe another resource.
            if "anchor" in params:
                continue
            rel = rel_tokens(params.get("rel", ""))
            link_type = rel_link_type(rel, params, _HEADER_TYPES)
            if link_type is not None:
                yield link_type, link_value[1], rel, params


def _unquoted(value: str) -> str:
    value = value.strip("\t ")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return _QUOTED_PAIR.sub(r"\1", value[1:-1])
    return value
