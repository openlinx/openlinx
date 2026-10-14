"""The Page extractor: the columns a Page's HTML gives (030-add-page-data D1, D7)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.pages import Extractor, PageInput
from spider.extract.text import normalized


class PageData(msgspec.Struct, frozen=True, kw_only=True):
    title_1: str | None
    title_1_length: int | None


def extract_page_data(tree: LexborHTMLParser, page: PageInput) -> PageData:
    node = tree.css_first("title")
    title = None if node is None else normalized(node.text())
    return PageData(title_1=title, title_1_length=None if title is None else len(title))


PAGE_DATA = Extractor("page_data", extract_page_data)
