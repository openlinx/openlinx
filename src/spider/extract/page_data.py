"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages import Extractor, PageInput
from spider.extract.text import normalized

_FOREIGN = frozenset({"svg", "math"})


class PageData(msgspec.Struct, frozen=True, kw_only=True):
    title_1: str | None
    title_1_length: int | None
    title_2: str | None
    title_count: int


def extract_page_data(tree: LexborHTMLParser, page: PageInput) -> PageData:
    titles = [normalized(node.text()) for node in tree.css("title") if not _in_foreign(node)]
    first = _nth(titles, 0)
    return PageData(
        title_1=first,
        title_1_length=None if first is None else len(first),
        title_2=_nth(titles, 1),
        title_count=len(titles),
    )


def _nth(texts: list[str], index: int) -> str | None:
    return texts[index] if index < len(texts) else None


def _in_foreign(node: LexborNode) -> bool:
    """Inside SVG or MathML, whose title elements are no Page title."""
    parent = node.parent
    while parent is not None:
        if parent.tag in _FOREIGN:
            return True
        parent = parent.parent
    return False


PAGE_DATA = Extractor("page_data", extract_page_data)
