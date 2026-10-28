"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import math
import re
from collections.abc import Collection, Iterator
from fractions import Fraction

from selectolax.lexbor import LexborNode

# ASCII whitespace only, as document.title has it: a no-break space is text.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_WHITESPACE_RUN = re.compile(f"[{_ASCII_WHITESPACE}]+")
# Their content is no text of the Page: code, styles, fallbacks, frames and pictures. The
# Page extractor leaves out elements inside svg and math the same way. Parsed with scripting
# on, noscript holds its content as one text node. lexbor keeps template content out of the
# tree; template stays here for a parser that does not.
_SKIPPED = frozenset({"script", "style", "noscript", "template", "iframe", "svg", "math"})
# A break at their start and end separates the words of the text around them.
_BLOCKS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
# Whitespace, which normalising makes one space.
_BREAK = " "
# On the walk's stack: the end of a block element's content.
_BLOCK_END = object()


def normalized(text: str) -> str:
    return trimmed(_WHITESPACE_RUN.sub(" ", text))


def rounded(value: Fraction) -> float:
    """To 2 decimals, half up, from the exact value: a float would round 3.125 down."""
    return math.floor(value * 100 + Fraction(1, 2)) / 100


def trimmed(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)


def element_text(element: LexborNode) -> str:
    return _BREAK.join(text_blocks(element))


def text_blocks(element: LexborNode, excluded: Collection[int] = ()) -> Iterator[str]:
    """The text of the element's content, as the blocks that `br` and block elements break,
    leaving out the elements whose mem_id is in `excluded`."""
    # An explicit stack, so a deep tree needs no recursion.
    parts: list[str] = []
    pending: list[LexborNode | object | None] = [element.first_child]
    while pending:
        node = pending.pop()
        if node is None:
            continue
        if not isinstance(node, LexborNode):
            if parts:
                yield "".join(parts)
                parts.clear()
            continue
        pending.append(node.next)
        if node.is_text_node:
            parts.append(node.text_content or "")
        elif node.tag == "br" or node.tag in _BLOCKS:
            if parts:
                yield "".join(parts)
                parts.clear()
            if node.tag in _BLOCKS and node.mem_id not in excluded:
                pending.extend((_BLOCK_END, node.first_child))
        elif node.tag not in _SKIPPED and node.mem_id not in excluded:
            pending.append(node.first_child)
    if parts:
        yield "".join(parts)
