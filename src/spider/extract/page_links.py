"""The Link extractor: what the element of each HTML Link says (030-add-page-data D4)."""

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages.links import locate_links
from spider.crawl.pages.preparation import PageInput, extractor
from spider.crawl.references import DiscoveredLink
from spider.extract.text import element_text, normalized


class LinkAttributes(msgspec.Struct, frozen=True, kw_only=True):
    ordinal: int
    anchor_text: str | None
    alt_text: str | None


class PageLinks(msgspec.Struct, frozen=True, kw_only=True):
    links: tuple[LinkAttributes, ...]


def extract_page_links(tree: LexborHTMLParser, page: PageInput, config: None) -> PageLinks:
    return PageLinks(
        links=tuple(
            LinkAttributes(
                ordinal=link.ordinal,
                anchor_text=_anchor_text(link, element),
                alt_text=_alt_text(link, element),
            )
            for link, element, _ in locate_links(tree, page.links)
        )
    )


def _anchor_text(link: DiscoveredLink, element: LexborNode) -> str | None:
    if link.type != "hyperlink":
        return None
    return normalized(element_text(element))


def _alt_text(link: DiscoveredLink, element: LexborNode) -> str | None:
    # An <img>'s src and srcset Links both carry its alt; <img alt> is the empty string.
    if link.type != "image" or element.tag != "img" or "alt" not in element.attributes:
        return None
    return normalized(element.attributes["alt"] or "")


PAGE_LINKS = extractor("page_links", extract_page_links, None)
