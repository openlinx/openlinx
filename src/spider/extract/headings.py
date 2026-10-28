"""The h1 and h2 headings of a Page's HTML (030-add-page-data D7)."""

from selectolax.lexbor import LexborHTMLParser

from spider.extract.head_metadata import page_nodes
from spider.extract.text import element_text, normalized


def headings(tree: LexborHTMLParser, tag: str) -> tuple[list[str], int]:
    # Only the first two texts are stored, and the parser nests an h1 inside a div inside an
    # h1, so each heading may hold every later one: reading them all cost their count squared.
    nodes = page_nodes(tree, tag)
    return [normalized(element_text(node)) for node in nodes[:2]], len(nodes)
