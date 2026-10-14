"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.pages import Extractor, PageInput


class PageData(msgspec.Struct, frozen=True, kw_only=True):
    title_1: str | None


def extract_page_data(tree: LexborHTMLParser, page: PageInput) -> PageData:
    title = tree.css_first("title")
    return PageData(title_1=None if title is None else title.text())


PAGE_DATA = Extractor("page_data", extract_page_data)
