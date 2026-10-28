"""The Content Area, the counts and the hash of its text, and Text Ratio (030-add-page-data D7,
D8, D10, D13)."""

import hashlib
import math
import re
from collections.abc import Iterable, Iterator
from fractions import Fraction

from selectolax.lexbor import LexborHTMLParser

from spider.extract.content_area import ContentArea
from spider.extract.text import element_text, joined, normalized, text_blocks
from spider.extract.unicode_scripts import HAN_AND_KANA, MARKS, WORD_CHARACTERS


def _class(ranges: Iterable[tuple[int, int]]) -> str:
    return "[" + "".join(f"\\U{first:08x}-\\U{last:08x}" for first, last in ranges) + "]"


# Python's re has no Unicode properties, and its \w takes "_" and leaves out marks. The tables
# are of one Unicode version, so a count does not change with the interpreter's.
_WORD_CHARACTER = _class(WORD_CHARACTERS)
# Each Han or kana character is a word of its own, with the marks after it, such as a
# decomposed voiced sound mark or a variation selector.
_ONE_CHARACTER_WORD = f"{_class(HAN_AND_KANA)}{_class(MARKS)}*"
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


def average_words_per_sentence(words: int, sentences: int) -> float | None:
    return _rounded(Fraction(words, sentences)) if sentences else None


def content_hash(blocks: Iterable[str]) -> str:
    # No Unicode normalisation: its tables differ between interpreters (D10).
    return hashlib.sha256(normalized(joined(blocks)).encode()).hexdigest()


def text_ratio_pct(tree: LexborHTMLParser, length: int) -> float | None:
    if length == 0:
        return None
    text = "" if tree.body is None else normalized(element_text(tree.body))
    return _rounded(Fraction(100 * len(text), length))


def _rounded(value: Fraction) -> float:
    """To 2 decimals, half up, from the exact value: a float would round 3.125 down."""
    return math.floor(value * 100 + Fraction(1, 2)) / 100
