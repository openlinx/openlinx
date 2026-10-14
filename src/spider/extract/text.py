"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import re

from selectolax.lexbor import LexborNode

# ASCII whitespace only, as document.title has it: a no-break space is text.
_ASCII_WHITESPACE = "\t\n\x0c\r "
_WHITESPACE_RUN = re.compile(f"[{_ASCII_WHITESPACE}]+")
# Their content is no text of the Page: code, styles, fallbacks, frames and pictures.
_SKIPPED = frozenset({"script", "style", "noscript", "template", "iframe", "svg", "math"})


def normalized(text: str) -> str:
    return trimmed(_WHITESPACE_RUN.sub(" ", text))


def trimmed(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)


def element_text(element: LexborNode) -> str:
    """Its text nodes in document order, with an explicit stack: a deep tree needs no recursion."""
    parts: list[str] = []
    pending: list[LexborNode | None] = [element.first_child]
    while pending:
        node = pending.pop()
        if node is None:
            continue
        pending.append(node.next)
        if node.is_text_node:
            parts.append(node.text_content or "")
        elif node.tag not in _SKIPPED:
            pending.append(node.first_child)
    return "".join(parts)
