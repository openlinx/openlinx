"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import re

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


def normalized(text: str) -> str:
    return trimmed(_WHITESPACE_RUN.sub(" ", text))


def trimmed(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)


def element_text(element: LexborNode) -> str:
    # An explicit stack, so a deep tree needs no recursion.
    parts: list[str] = []
    pending: list[LexborNode | str | None] = [element.first_child]
    while pending:
        node = pending.pop()
        if node is None:
            continue
        if isinstance(node, str):
            parts.append(node)
            continue
        pending.append(node.next)
        if node.is_text_node:
            parts.append(node.text_content or "")
        elif node.tag == "br":
            parts.append(_BREAK)
        elif node.tag in _BLOCKS:
            parts.append(_BREAK)
            pending.extend((_BREAK, node.first_child))
        elif node.tag not in _SKIPPED:
            pending.append(node.first_child)
    return "".join(parts)
