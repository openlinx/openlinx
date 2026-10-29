"""The Link extractor: what the element of each HTML Link says (030-add-page-data D4)."""

from collections.abc import Mapping

import msgspec
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.crawl.pages.links import locate_links
from spider.crawl.pages.preparation import PageInput, extractor
from spider.crawl.references import DiscoveredLink
from spider.extract.text import element_text, normalized, trimmed
from spider.store.page_records import LinkPosition

_SECTIONS: Mapping[str, LinkPosition] = {
    "nav": "navigation",
    "header": "header",
    "footer": "footer",
    "aside": "sidebar",
}


class LinkAttributes(msgspec.Struct, frozen=True, kw_only=True):
    ordinal: int
    anchor_text: str | None
    alt_text: str | None
    hreflang: str | None
    media: str | None
    link_position: LinkPosition


class PageLinks(msgspec.Struct, frozen=True, kw_only=True):
    links: tuple[LinkAttributes, ...]


def extract_page_links(tree: LexborHTMLParser, page: PageInput, config: None) -> PageLinks:
    # Many Links share their ancestors, so each element's position is found once.
    positions: dict[int, LinkPosition] = {}
    return PageLinks(
        links=tuple(
            LinkAttributes(
                ordinal=link.ordinal,
                anchor_text=_anchor_text(link, element),
                alt_text=_alt_text(link, element),
                hreflang=_attribute(link, element, "hreflang", "hreflang"),
                media=_attribute(link, element, "mobile_alternate", "media"),
                link_position=_position(link, placing, positions),
            )
            for link, element, placing in locate_links(tree, page.links)
        )
    )


def _anchor_text(link: DiscoveredLink, element: LexborNode) -> str | None:
    if link.type != "hyperlink":
        return None
    if element.tag == "area":
        return normalized(element.attributes.get("alt") or "")
    text = normalized(element_text(element))
    if text:
        return text
    # A logo or an icon as the whole link: what its images say is the link's text.
    return normalized(" ".join(img.attributes.get("alt") or "" for img in element.css("img")))


def _alt_text(link: DiscoveredLink, element: LexborNode) -> str | None:
    # An <img>'s src and srcset Links both carry its alt; <img alt> is the empty string.
    if link.type != "image" or element.tag != "img" or "alt" not in element.attributes:
        return None
    return normalized(element.attributes["alt"] or "")


def _attribute(link: DiscoveredLink, element: LexborNode, link_type: str, name: str) -> str | None:
    if link.type != link_type:
        return None
    return trimmed(element.attributes.get(name) or "")


def _position(
    link: DiscoveredLink, placing: LexborNode, positions: dict[int, LinkPosition]
) -> LinkPosition:
    if link.declared_in == "head":
        return "head"
    below: list[int] = []
    position: LinkPosition = "content"
    node = placing.parent
    while node is not None and node.tag not in ("body", "html"):
        if node.mem_id in positions:
            position = positions[node.mem_id]
            break
        section = _SECTIONS.get(node.tag or "")
        if section is not None:
            position = section
            break
        below.append(node.mem_id)
        node = node.parent
    positions.update(dict.fromkeys(below, position))
    return position


PAGE_LINKS = extractor("page_links", extract_page_links, None)
