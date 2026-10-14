"""The robots directives parser, which 030 imports for its directive columns (020 D6)."""

from collections.abc import Iterable

import msgspec
from selectolax.lexbor import LexborHTMLParser


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
    return RobotsDirectives(
        meta_robots=", ".join(meta) if meta else None,
        meta_robots_noindex="noindex" in meta_tokens,
        meta_robots_nofollow="nofollow" in meta_tokens,
        x_robots_tag=None,
        x_robots_tag_noindex=False,
        x_robots_tag_nofollow=False,
    )


def _normalised(value: str) -> str:
    return " ".join(value.split())


def _directives(values: Iterable[str]) -> set[str]:
    return {part.strip().lower() for value in values for part in value.split(",")}
