"""The Content Area and the counts taken over its text (030-add-page-data D7, D8, D13)."""

import re
from collections.abc import Iterable, Iterator

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.extract.text import text_blocks


class ContentArea(msgspec.Struct, frozen=True, kw_only=True):
    """The Page extractor's config: the [content_area] selectors, compiled by each parser."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ("nav", "header", "footer")


_WORD = re.compile(r"[^\W_]+")


def content_blocks(tree: LexborHTMLParser, area: ContentArea) -> Iterator[str]:
    """The Content Area text, block by block, in document order."""
    excluded = {node.mem_id for selector in area.exclude for node in tree.css(selector)}
    for root in _roots(tree, area):
        if not any(node.mem_id in excluded for node in _with_ancestors(root)):
            yield from text_blocks(root, excluded)


def _roots(tree: LexborHTMLParser, area: ContentArea) -> list[LexborNode]:
    if not area.include:
        return [] if tree.body is None else [tree.body]
    # One selector list gives the matches in document order, a node that two selectors
    # match twice.
    matches = list({node.mem_id: node for node in tree.css(", ".join(area.include))}.values())
    matched = {node.mem_id for node in matches}
    return [
        node
        for node in matches
        if not any(above.mem_id in matched for above in _with_ancestors(node.parent))
    ]


def _with_ancestors(node: LexborNode | None) -> Iterator[LexborNode]:
    while node is not None:
        yield node
        node = node.parent


def word_count(blocks: Iterable[str]) -> int:
    return sum(len(_WORD.findall(block)) for block in blocks)
