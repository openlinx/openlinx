"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages import Extractor, PageInput
from spider.extract.text import element_text, normalized, trimmed

_IGNORED_ANCESTORS = frozenset({"svg", "math", "noscript"})


class PageData(msgspec.Struct, frozen=True, kw_only=True):
    title_1: str | None
    title_1_length: int | None
    title_2: str | None
    title_2_length: int | None
    title_count: int
    meta_description_1: str | None
    meta_description_1_length: int | None
    meta_description_2: str | None
    meta_description_2_length: int | None
    meta_description_count: int
    meta_keywords_1: str | None
    meta_keywords_1_length: int | None
    h1_1: str | None
    h1_1_length: int | None
    h1_2: str | None
    h1_2_length: int | None
    h1_count: int
    h2_1: str | None
    h2_1_length: int | None
    h2_2: str | None
    h2_2_length: int | None
    h2_count: int


def extract_page_data(tree: LexborHTMLParser, page: PageInput) -> PageData:
    titles = [normalized(node.text()) for node in _page_nodes(tree, "title")]
    first, second = _nth(titles, 0), _nth(titles, 1)
    descriptions = _meta_contents(tree, "description")
    description_1, description_2 = _nth(descriptions, 0), _nth(descriptions, 1)
    keywords = _nth(_meta_contents(tree, "keywords"), 0)
    h1s, h2s = _headings(tree, "h1"), _headings(tree, "h2")
    first_h1, second_h1, first_h2, second_h2 = (
        _nth(h1s, 0),
        _nth(h1s, 1),
        _nth(h2s, 0),
        _nth(h2s, 1),
    )
    return PageData(
        title_1=first,
        title_1_length=_length(first),
        title_2=second,
        title_2_length=_length(second),
        title_count=len(titles),
        meta_description_1=description_1,
        meta_description_1_length=_length(description_1),
        meta_description_2=description_2,
        meta_description_2_length=_length(description_2),
        meta_description_count=len(descriptions),
        meta_keywords_1=keywords,
        meta_keywords_1_length=_length(keywords),
        h1_1=first_h1,
        h1_1_length=_length(first_h1),
        h1_2=second_h1,
        h1_2_length=_length(second_h1),
        h1_count=len(h1s),
        h2_1=first_h2,
        h2_1_length=_length(first_h2),
        h2_2=second_h2,
        h2_2_length=_length(second_h2),
        h2_count=len(h2s),
    )


def _headings(tree: LexborHTMLParser, tag: str) -> list[str]:
    return [normalized(element_text(node)) for node in _page_nodes(tree, tag)]


def _page_nodes(tree: LexborHTMLParser, selector: str) -> list[LexborNode]:
    return [node for node in tree.css(selector) if not _has_ignored_ancestor(node)]


def _meta_contents(tree: LexborHTMLParser, name: str) -> list[str]:
    """The normalised content of each meta element of that name; one without content gives ""."""
    return [
        normalized(node.attributes.get("content") or "")
        for node in _page_nodes(tree, "meta")
        if _is_named(node, name)
    ]


def _is_named(node: LexborNode, name: str) -> bool:
    value = trimmed(node.attributes.get("name") or "")
    # HTML compares attribute values ASCII case-insensitively, so a Kelvin sign is no k.
    return value.isascii() and value.lower() == name


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
