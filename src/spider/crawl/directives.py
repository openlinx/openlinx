"""The robots directives parser, which 030 imports for its directive columns (020 D6)."""

import re
from collections.abc import Iterable

import msgspec
from selectolax.lexbor import LexborHTMLParser

# A header value that starts with a name and a colon applies only to the crawler it names.
_PREFIX = re.compile(r"\s*([^\s:,]+)\s*:")
_NOINDEX = frozenset({"noindex", "none"})
_NOFOLLOW = frozenset({"nofollow", "none"})


class RobotsDirectives(msgspec.Struct, frozen=True, kw_only=True):
    """Named as 030's columns, so the two changes never disagree about noindex or nofollow."""

    meta_robots: str | None
    meta_robots_noindex: bool
    meta_robots_nofollow: bool
    x_robots_tag: str | None
    x_robots_tag_noindex: bool
    x_robots_tag_nofollow: bool


def meta_robots_contents(tree: LexborHTMLParser) -> list[str]:
    """The `content` of every `<meta name="robots">`, in document order."""
    return [
        node.attributes.get("content") or ""
        for node in tree.css("meta[name]")
        if (node.attributes.get("name") or "").strip().lower() == "robots"
    ]


def robots_directives(
    meta_contents: Iterable[str], header_values: Iterable[str], token: str
) -> RobotsDirectives:
    meta = [_normalised(content) for content in meta_contents]
    meta_tokens = _directives(meta)
    header = [_normalised(value) for value in header_values]
    header_tokens = _directives(
        applying for value in header if (applying := _applying(value, token)) is not None
    )
    return RobotsDirectives(
        meta_robots=", ".join(meta) if meta else None,
        meta_robots_noindex=not meta_tokens.isdisjoint(_NOINDEX),
        meta_robots_nofollow=not meta_tokens.isdisjoint(_NOFOLLOW),
        x_robots_tag=", ".join(header) if header else None,
        x_robots_tag_noindex=not header_tokens.isdisjoint(_NOINDEX),
        x_robots_tag_nofollow=not header_tokens.isdisjoint(_NOFOLLOW),
    )


def _applying(value: str, token: str) -> str | None:
    """The directives of a header value for the robots token; None for another crawler."""
    prefix = _PREFIX.match(value)
    if prefix is None:
        return value
    return value[prefix.end() :] if prefix[1].lower() == token.lower() else None


def _normalised(value: str) -> str:
    return " ".join(value.split())


def _directives(values: Iterable[str]) -> set[str]:
    return {part.strip().lower() for value in values for part in value.split(",")}
