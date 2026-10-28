"""The Content Area and the counts taken over its text (030-add-page-data D7, D8, D13)."""

import re
import sys
import unicodedata
from collections.abc import Iterable, Iterator

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.extract.text import text_blocks
from spider.extract.unicode_scripts import IDEOGRAPHS


class ContentArea(msgspec.Struct, frozen=True, kw_only=True):
    """The Page extractor's config: the [content_area] selectors, compiled by each parser."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ("nav", "header", "footer")


def _class(points: Iterable[int]) -> str:
    ranges: list[list[int]] = []
    for point in points:
        if ranges and ranges[-1][1] == point - 1:
            ranges[-1][1] = point
        else:
            ranges.append([point, point])
    return "[" + "".join(f"\\U{first:08x}-\\U{last:08x}" for first, last in ranges) + "]"


_IDEOGRAPHS = frozenset(point for first, last in IDEOGRAPHS for point in range(first, last + 1))
# Letters, marks and numbers (L, M, N) but the ideographs: Python's re has no Unicode
# properties, and its \w takes "_" and leaves out marks.
_WORD_CHARACTER = _class(
    point
    for point in range(sys.maxunicode + 1)
    if unicodedata.category(chr(point))[0] in "LMN" and point not in _IDEOGRAPHS
)
# A single apostrophe, hyphen, full stop or comma between two word characters.
_JOINER = "['\u2019\\-\u2010.,]"
# Each ideograph is a word of its own.
_WORD = re.compile(
    f"{_class(sorted(_IDEOGRAPHS))}|{_WORD_CHARACTER}+(?:{_JOINER}{_WORD_CHARACTER}+)*"
)

_TERMINATORS = ".!?\u2026\u3002\uff01\uff1f"
# A run of terminators ends a sentence before whitespace or the block's end, or wherever it
# holds a full-width one, which needs no space after it.
_SENTENCE_END = re.compile(
    f"[{_TERMINATORS}]*[\u3002\uff01\uff1f][{_TERMINATORS}]*|[{_TERMINATORS}]+(?=\\s|$)"
)


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


def sentence_count(blocks: Iterable[str]) -> int:
    return sum(
        1
        for block in blocks
        for part in _SENTENCE_END.split(block)
        if _WORD.search(part) is not None
    )


def word_count(blocks: Iterable[str]) -> int:
    return sum(len(_WORD.findall(block)) for block in blocks)
