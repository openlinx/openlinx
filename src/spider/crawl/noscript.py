"""`<noscript>` read as a browser that runs scripts reads it (020-add-crawl-core D5, task 15.1)."""

import re
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.naming import APP_NAME

# On a renamed <noscript>: the index of its text, which also tells it from a page's <template>.
MARKER = f"data-{APP_NAME}-noscript"
# A tag name ends at white space, a slash or a closing bracket (HTML's tokenizer).
_NOSCRIPT_TAG = re.compile(r"<(/?)noscript(?=[\t\n\x0c\r />]|$)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedHtml:
    tree: LexborHTMLParser
    # The text of each <noscript>, by the index its template carries, as text: a page's own
    # template may carry any value.
    noscripts: Mapping[str, str]

    def noscript_text(self, node: LexborNode) -> str | None:
        """None for a page's own `<template>`."""
        return self.noscripts.get(node.attributes.get(MARKER) or "")


def parse_html(text: str) -> ParsedHtml:
    renamed, noscripts = without_noscript(text)
    return ParsedHtml(LexborHTMLParser(renamed), {str(i): text for i, text in enumerate(noscripts)})


def without_noscript(text: str) -> tuple[str, tuple[str, ...]]:
    """Every `<noscript>` tag renamed to a `<template>` tag, which lexbor keeps in `<head>` and
    out of the tree, and the text of each `<noscript>` as a browser that runs scripts reads it:
    from its start tag's `>` to the next `</noscript>`."""
    tags = list(_NOSCRIPT_TAG.finditer(text))
    if not tags:
        return text, ()
    ends = [tag.start() for tag in tags if tag[1]]
    parts: list[str] = []
    noscripts: list[str] = []
    position = 0
    # The first ">" after the latest start tag: it stays the first for every later start tag
    # before it, so a page of unclosed start tags is read once, not once per tag.
    closing = 0
    for tag in tags:
        parts.append(text[position : tag.start()])
        position = tag.end()
        if tag[1]:
            parts.append("</template")
            continue
        if closing != -1 and closing < tag.end():
            closing = text.find(">", tag.end())
        parts.append(f'<template {MARKER}="{len(noscripts)}"')
        if closing == -1:
            noscripts.append("")
            continue
        following = bisect_right(ends, closing)
        end = ends[following] if following < len(ends) else len(text)
        noscripts.append(text[closing + 1 : end])
    parts.append(text[position:])
    return "".join(parts), tuple(noscripts)
