"""The Content Area and the counts taken over its text (030-add-page-data D7, D8, D13)."""

import re
import sys
import unicodedata
from collections.abc import Iterable, Iterator

from selectolax.lexbor import LexborHTMLParser

from spider.extract.content_area import ContentArea
from spider.extract.text import text_blocks
from spider.extract.unicode_scripts import HAN_AND_KANA


def _class(points: Iterable[int]) -> str:
    ranges: list[list[int]] = []
    for point in points:
        if ranges and ranges[-1][1] == point - 1:
            ranges[-1][1] = point
        else:
            ranges.append([point, point])
    return "[" + "".join(f"\\U{first:08x}-\\U{last:08x}" for first, last in ranges) + "]"


_HAN_AND_KANA = frozenset(point for first, last in HAN_AND_KANA for point in range(first, last + 1))


def _word_and_mark_classes() -> tuple[str, str]:
    # One pass over the code points, which costs most of this module's import time.
    word: list[int] = []
    mark: list[int] = []
    for point in range(sys.maxunicode + 1):
        group = unicodedata.category(chr(point))[0]
        if group in "LMN" and point not in _HAN_AND_KANA:
            word.append(point)
        if group == "M":
            mark.append(point)
    return _class(word), _class(mark)


# Letters, marks and numbers (L, M, N) but Han and kana: Python's re has no Unicode
# properties, and its \w takes "_" and leaves out marks.
_WORD_CHARACTER, _MARK = _word_and_mark_classes()
# Each Han or kana character is a word of its own, with the marks after it, such as a
# decomposed voiced sound mark or a variation selector.
_ONE_CHARACTER_WORD = (
    "[" + "".join(f"\\U{a:08x}-\\U{b:08x}" for a, b in HAN_AND_KANA) + f"]{_MARK}*"
)
# A single apostrophe, hyphen, full stop or comma between two word characters.
_JOINER = "['\u2019\\-\u2010.,]"
_WORD = re.compile(f"{_ONE_CHARACTER_WORD}|{_WORD_CHARACTER}+(?:{_JOINER}{_WORD_CHARACTER}+)*")

_TERMINATORS = ".!?\u2026\u3002\uff01\uff1f"
# A run of terminators ends a sentence before whitespace or the block's end, or wherever it
# holds a full-width one, which needs no space after it.
_SENTENCE_END = re.compile(
    f"[{_TERMINATORS}]*[\u3002\uff01\uff1f][{_TERMINATORS}]*|[{_TERMINATORS}]+(?=\\s|$)"
)


def content_blocks(tree: LexborHTMLParser, area: ContentArea) -> Iterator[str]:
    """The Content Area text, block by block, in document order."""
    body = tree.body
    if body is None:
        return
    # Each selector on its own: one selector list would let a selector that leaves a comment
    # or a string open swallow the ones after it.
    excluded = {node.mem_id for selector in area.exclude for node in tree.css(selector)}
    roots = {node.mem_id for selector in area.include for node in tree.css(selector)}
    # The walk starts inside <body>, so <body> and <html> are looked at here.
    outer = [node.mem_id for node in (body, body.parent) if node is not None]
    if any(mem_id in excluded for mem_id in outer):
        return
    every = not area.include or any(mem_id in roots for mem_id in outer)
    yield from text_blocks(body, excluded, None if every else roots)


def sentence_count(blocks: Iterable[str]) -> int:
    return sum(
        1
        for block in blocks
        for part in _SENTENCE_END.split(block)
        if _WORD.search(part) is not None
    )


def word_count(blocks: Iterable[str]) -> int:
    return sum(len(_WORD.findall(block)) for block in blocks)
