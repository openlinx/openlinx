"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages import PageInput, extractor
from spider.extract.text import element_text, normalized, trimmed

# An element inside svg or math names a picture or a formula; text inside them is left out too
# (text._SKIPPED). Page preparation has already turned each noscript into a template, whose
# content is out of the tree, as a browser that runs scripts reads it.
_PAGE_ELEMENT = ":not(svg *, math *)"


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


def extract_page_data(tree: LexborHTMLParser, page: PageInput, config: None) -> PageData:
    titles = [normalized(node.text()) for node in _page_nodes(tree, "title")]
    title_1, title_2 = _nth(titles, 0), _nth(titles, 1)
    metas = _page_nodes(tree, "meta")
    descriptions = _meta_contents(metas, "description")
    description_1, description_2 = _nth(descriptions, 0), _nth(descriptions, 1)
    keywords_1 = _nth(_meta_contents(metas, "keywords"), 0)
    h1s, h1_count = _headings(tree, "h1")
    h1_1, h1_2 = _nth(h1s, 0), _nth(h1s, 1)
    h2s, h2_count = _headings(tree, "h2")
    h2_1, h2_2 = _nth(h2s, 0), _nth(h2s, 1)
    return PageData(
        title_1=title_1,
        title_1_length=_length(title_1),
        title_2=title_2,
        title_2_length=_length(title_2),
        title_count=len(titles),
        meta_description_1=description_1,
        meta_description_1_length=_length(description_1),
        meta_description_2=description_2,
        meta_description_2_length=_length(description_2),
        meta_description_count=len(descriptions),
        meta_keywords_1=keywords_1,
        meta_keywords_1_length=_length(keywords_1),
        h1_1=h1_1,
        h1_1_length=_length(h1_1),
        h1_2=h1_2,
        h1_2_length=_length(h1_2),
        h1_count=h1_count,
        h2_1=h2_1,
        h2_1_length=_length(h2_1),
        h2_2=h2_2,
        h2_2_length=_length(h2_2),
        h2_count=h2_count,
    )


def _headings(tree: LexborHTMLParser, tag: str) -> tuple[list[str], int]:
    # Only the first two texts are stored, and the parser nests an h1 inside a div inside an
    # h1, so each heading may hold every later one: reading them all cost their count squared.
    nodes = _page_nodes(tree, tag)
    return [normalized(element_text(node)) for node in nodes[:2]], len(nodes)


def _page_nodes(tree: LexborHTMLParser, tag: str) -> list[LexborNode]:
    # The selector engine tests the ancestors: walking up from each node in Python cost the
    # node count times the depth, seconds per Page on a crafted deep document.
    return tree.css(tag + _PAGE_ELEMENT)


def _meta_contents(metas: list[LexborNode], name: str) -> list[str]:
    return [
        normalized(node.attributes.get("content") or "") for node in metas if _is_named(node, name)
    ]


def _is_named(node: LexborNode, name: str) -> bool:
    value = trimmed(node.attributes.get("name") or "")
    # HTML compares attribute values ASCII case-insensitively, so a Kelvin sign is no k.
    return value.isascii() and value.lower() == name


def _nth(texts: list[str], index: int) -> str | None:
    return texts[index] if index < len(texts) else None


def _length(text: str | None) -> int | None:
    return None if text is None else len(text)


PAGE_DATA = extractor("page_data", extract_page_data, None)
