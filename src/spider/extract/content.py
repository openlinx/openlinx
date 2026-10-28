"""The Content Area and the counts taken over its text (030-add-page-data D7, D8, D13)."""

import re
from collections.abc import Iterable, Iterator

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.extract.text import text_blocks


class ContentArea(msgspec.Struct, frozen=True, kw_only=True):
    """The Page extractor's config: the [content_area] selectors, compiled by each parser."""

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ("nav", "header", "footer")


_WORD = re.compile(r"[^\W_]+")


def content_blocks(tree: LexborHTMLParser, area: ContentArea) -> Iterator[str]:
    """The Content Area text, block by block, in document order."""
    if tree.body is None:
        return
    excluded = {node.mem_id for selector in area.exclude for node in tree.css(selector)}
    yield from text_blocks(tree.body, excluded)


def word_count(blocks: Iterable[str]) -> int:
    return sum(len(_WORD.findall(block)) for block in blocks)
