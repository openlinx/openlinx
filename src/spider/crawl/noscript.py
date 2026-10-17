"""`<noscript>` read as a browser that runs scripts reads it (020-add-crawl-core D5, task 15.1)."""

import re
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
    """Every `<noscript>` renamed to a `<template>`, which lexbor keeps in `<head>` and out of the
    tree, and its text as a browser that runs scripts reads it: from its start tag's `>` on."""
    parts: list[str] = []
    noscripts: list[str] = []
    position = 0
    # The text of the open <noscript> runs to the next end tag, or to the next start tag, which
    # closes it first: a literal start tag in a script must not swallow a real <noscript>, and
    # the texts never overlap. An end tag outside a range is left: it could close a <template>.
    opened: int | None = None
    for tag in _NOSCRIPT_TAG.finditer(text):
        if tag[1] and opened is None:
            continue
        parts.append(text[position : tag.start()])
        position = tag.end()
        if opened is not None:
            noscripts.append(_text_after_start_tag(text, opened, tag.start()))
            # A renamed end tag keeps its own ">"; a start tag needs a whole end tag before it.
            parts.append("</template" if tag[1] else "</template>")
            opened = None
        if not tag[1]:
            parts.append(f'<template {MARKER}="{len(noscripts)}"')
            opened = tag.end()
    if opened is not None:
        noscripts.append(_text_after_start_tag(text, opened, len(text)))
    if not noscripts:
        return text, ()
    parts.append(text[position:])
    return "".join(parts), tuple(noscripts)


def _text_after_start_tag(text: str, start: int, end: int) -> str:
    closing = text.find(">", start, end)
    return "" if closing == -1 else text[closing + 1 : end]
