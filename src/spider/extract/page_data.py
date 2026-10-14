"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages import Extractor, PageInput
from spider.extract.text import normalized

_IGNORED_ANCESTORS = frozenset({"svg", "math", "noscript"})


class PageData(msgspec.Struct, frozen=True, kw_only=True):
    title_1: str | None
    title_1_length: int | None
    title_2: str | None
    title_2_length: int | None
    title_count: int


def extract_page_data(tree: LexborHTMLParser, page: PageInput) -> PageData:
    titles = [
        normalized(node.text()) for node in tree.css("title") if not _has_ignored_ancestor(node)
    ]
    first, second = _nth(titles, 0), _nth(titles, 1)
    return PageData(
        title_1=first,
        title_1_length=_length(first),
        title_2=second,
        title_2_length=_length(second),
        title_count=len(titles),
    )


def _nth(texts: list[str], index: int) -> str | None:
    return texts[index] if index < len(texts) else None


def _length(text: str | None) -> int | None:
    return None if text is None else len(text)


def _has_ignored_ancestor(node: LexborNode) -> bool:
    """Inside SVG or MathML it names a picture or a formula. Inside noscript it is no element
    at all to a browser that runs scripts, as a search engine's renderer does: the parser here
    runs with scripting off, so it builds elements there."""
    parent = node.parent
    while parent is not None:
        if parent.tag in _IGNORED_ANCESTORS:
            return True
        parent = parent.parent
    return False


PAGE_DATA = Extractor("page_data", extract_page_data)
