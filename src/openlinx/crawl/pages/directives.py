"""The robots directives parser, which 030 imports for its columns (020-add-crawl-core D6)."""

import re
from collections.abc import Iterable

import msgspec
from selectolax.lexbor import LexborHTMLParser

# A header value that starts with a name and a colon applies only to the crawler it names.
_PREFIX = re.compile(r"\s*([^\s:,]+)\s*:")
# Directives that take a value after a colon, which no user-agent prefix is named after.
_VALUED = frozenset({"unavailable_after", "max-snippet", "max-image-preview", "max-video-preview"})
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

    @property
    def nofollow(self) -> bool:
        """A page-level nofollow, from either source: no hyperlink of the Page is followed."""
        return self.meta_robots_nofollow or self.x_robots_tag_nofollow


# A Page without robots metas or an X-Robots-Tag header, and a preparation that gave nothing.
NO_DIRECTIVES = RobotsDirectives(
    meta_robots=None,
    meta_robots_noindex=False,
    meta_robots_nofollow=False,
    x_robots_tag=None,
    x_robots_tag_noindex=False,
    x_robots_tag_nofollow=False,
)


def meta_robots_contents(tree: LexborHTMLParser) -> list[str]:
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
    if prefix is None or prefix[1].lower() in _VALUED:
        return value
    return value[prefix.end() :] if prefix[1].lower() == token.lower() else None


def _normalised(value: str) -> str:
    return " ".join(value.split())


def _directives(values: Iterable[str]) -> set[str]:
    return {part.strip().lower() for value in values for part in value.split(",")}
