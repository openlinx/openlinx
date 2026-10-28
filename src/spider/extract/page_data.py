"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7, D10, D20)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.pages.preparation import Extractor, PageInput, extractor
from spider.extract.content import (
    average_words_per_sentence,
    content_blocks,
    content_hash,
    sentence_count,
    text_ratio_pct,
    word_count,
)
from spider.extract.content_area import ContentArea
from spider.extract.head_metadata import (
    declared_language,
    first_two,
    meta_contents,
    meta_refresh,
    page_nodes,
    titles,
)
from spider.extract.headings import headings
from spider.extract.structured_data import structured_data


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
    meta_refresh: str | None
    word_count: int
    sentence_count: int
    average_words_per_sentence: float | None
    text_ratio_pct: float | None
    declared_language: str | None
    content_hash: str | None
    jsonld_items: int
    microdata_items: int
    jsonld_parse_errors: int
    structured_data_types: tuple[str, ...]


def extract_page_data(tree: LexborHTMLParser, page: PageInput, config: ContentArea) -> PageData:
    title_texts = titles(tree)
    title_1, title_1_length, title_2, title_2_length = first_two(title_texts)
    metas = page_nodes(tree, "meta")
    descriptions = meta_contents(metas, "description")
    description_1, description_1_length, description_2, description_2_length = first_two(
        descriptions
    )
    keywords_1, keywords_1_length, _, _ = first_two(meta_contents(metas, "keywords"))
    h1s, h1_count = headings(tree, "h1")
    h1_1, h1_1_length, h1_2, h1_2_length = first_two(h1s)
    h2s, h2_count = headings(tree, "h2")
    h2_1, h2_1_length, h2_2, h2_2_length = first_two(h2s)
    blocks = list(content_blocks(tree, config))
    words, sentences = word_count(blocks), sentence_count(blocks)
    found = structured_data(tree)
    return PageData(
        title_1=title_1,
        title_1_length=title_1_length,
        title_2=title_2,
        title_2_length=title_2_length,
        title_count=len(title_texts),
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
        meta_refresh=meta_refresh(metas),
        word_count=words,
        sentence_count=sentences,
        average_words_per_sentence=average_words_per_sentence(words, sentences),
        text_ratio_pct=text_ratio_pct(tree, page.length),
        declared_language=declared_language(tree),
        content_hash=content_hash(blocks, words),
        jsonld_items=found.jsonld_items,
        microdata_items=found.microdata_items,
        jsonld_parse_errors=found.jsonld_parse_errors,
        structured_data_types=found.structured_data_types,
    )


def page_data_extractor(area: ContentArea) -> Extractor[ContentArea, PageData]:
    return extractor("page_data", extract_page_data, area)


PAGE_DATA = page_data_extractor(ContentArea())
