"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

from fractions import Fraction

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages.preparation import Extractor, PageInput, extractor
from spider.extract.content import ContentArea, content_blocks, sentence_count, word_count
from spider.extract.text import element_text, normalized, rounded, trimmed

# An element inside svg or math names a picture or a formula; text inside them is left out too
# (text._SKIPPED). Page preparation parses with scripting on, as a browser that runs scripts
# does, so a noscript holds text and no element.
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
    word_count: int
    sentence_count: int
    average_words_per_sentence: float | None
    text_ratio_pct: float | None
    declared_language: str | None


def extract_page_data(tree: LexborHTMLParser, page: PageInput, config: ContentArea) -> PageData:
    titles = [normalized(node.text()) for node in _page_nodes(tree, "title")]
    title_1, title_1_length, title_2, title_2_length = _first_two(titles)
    metas = _page_nodes(tree, "meta")
    descriptions = _meta_contents(metas, "description")
    description_1, description_1_length, description_2, description_2_length = _first_two(
        descriptions
    )
    keywords_1, keywords_1_length, _, _ = _first_two(_meta_contents(metas, "keywords"))
    h1s, h1_count = _headings(tree, "h1")
    h1_1, h1_1_length, h1_2, h1_2_length = _first_two(h1s)
    h2s, h2_count = _headings(tree, "h2")
    blocks = list(content_blocks(tree, config))
    words, sentences = word_count(blocks), sentence_count(blocks)
    h2_1, h2_1_length, h2_2, h2_2_length = _first_two(h2s)
    return PageData(
        title_1=title_1,
        title_1_length=title_1_length,
        title_2=title_2,
        title_2_length=title_2_length,
        title_count=len(titles),
        meta_description_1=description_1,
        meta_description_1_length=description_1_length,
        meta_description_2=description_2,
        meta_description_2_length=description_2_length,
        meta_description_count=len(descriptions),
        meta_keywords_1=keywords_1,
        meta_keywords_1_length=keywords_1_length,
        h1_1=h1_1,
        h1_1_length=h1_1_length,
        h1_2=h1_2,
        h1_2_length=h1_2_length,
        h1_count=h1_count,
        h2_1=h2_1,
        h2_1_length=h2_1_length,
        h2_2=h2_2,
        h2_2_length=h2_2_length,
        h2_count=h2_count,
        word_count=words,
        sentence_count=sentences,
        average_words_per_sentence=rounded(Fraction(words, sentences)) if sentences else None,
        text_ratio_pct=_text_ratio(tree, page.length),
        declared_language=_declared_language(tree),
    )


def _text_ratio(tree: LexborHTMLParser, length: int) -> float | None:
    if length == 0:
        return None
    text = "" if tree.body is None else normalized(element_text(tree.body))
    return rounded(Fraction(100 * len(text), length))


def _declared_language(tree: LexborHTMLParser) -> str | None:
    attributes = {} if tree.root is None else tree.root.attributes
    if "lang" not in attributes:
        return None
    # <html lang> has the attribute with no value.
    return trimmed(attributes["lang"] or "")


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


def _first_two(texts: list[str]) -> tuple[str | None, int | None, str | None, int | None]:
    first = texts[0] if texts else None
    second = texts[1] if len(texts) > 1 else None
    return first, _length(first), second, _length(second)


def _length(text: str | None) -> int | None:
    return None if text is None else len(text)


def page_data_extractor(area: ContentArea) -> Extractor[ContentArea, PageData]:
    return extractor("page_data", extract_page_data, area)


PAGE_DATA = page_data_extractor(ContentArea())
