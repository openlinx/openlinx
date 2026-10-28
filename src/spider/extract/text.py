"""Text of the HTML, as one model for every column (030-add-page-data D7)."""

import re
from collections.abc import Collection, Iterator

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


class _BlockEnd:
    """On the walk's stack: the end of a block element's content, or of a root's."""


_BLOCK_END = _BlockEnd()


def normalized(text: str) -> str:
    return trimmed(_WHITESPACE_RUN.sub(" ", text))


def trimmed(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE)


def element_text(element: LexborNode) -> str:
    return _BREAK.join(text_blocks(element))


def text_blocks(
    element: LexborNode, excluded: Collection[int] = (), roots: Collection[int] | None = None
) -> Iterator[str]:
    """The text of the element's content, as the blocks that `br` and block elements break,
    leaving out the elements whose mem_id is in `excluded`. With `roots`, only the text inside
    an element whose mem_id is in it counts, and each such root is a block of its own."""
    # An explicit stack, so a deep tree needs no recursion. Each entry carries whether it is
    # inside a root, so no node looks at its ancestors.
    parts: list[str] = []
    pending: list[tuple[LexborNode | None, bool] | _BlockEnd] = [
        (element.first_child, roots is None)
    ]
    while pending:
        entry = pending.pop()
        if isinstance(entry, _BlockEnd):
            if parts:
                yield "".join(parts)
                parts.clear()
            continue
        node, inside = entry
        if node is None:
            continue
        pending.append((node.next, inside))
        if node.is_text_node:
            if inside:
                parts.append(node.text_content or "")
            continue
        starts_root = not inside and roots is not None and node.mem_id in roots
        breaks = node.tag in _BLOCKS or starts_root
        if (breaks or node.tag == "br") and parts:
            yield "".join(parts)
            parts.clear()
        if node.tag == "br" or node.tag in _SKIPPED or node.mem_id in excluded:
            continue
        if breaks:
            pending.append(_BLOCK_END)
        pending.append((node.first_child, inside or starts_root))
    if parts:
        yield "".join(parts)
