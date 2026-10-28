"""The titles, meta elements and declared language of a Page's HTML (030-add-page-data D1, D7)."""

from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.extract.text import normalized, trimmed

# An element inside svg or math names a picture or a formula; text inside them is left out too
# (text._SKIPPED). Page preparation parses with scripting on, as a browser that runs scripts
# does, so a noscript holds text and no element.
_PAGE_ELEMENT = ":not(svg *, math *)"


def page_nodes(tree: LexborHTMLParser, tag: str) -> list[LexborNode]:
    # The selector engine tests the ancestors: walking up from each node in Python cost the
    # node count times the depth, seconds per Page on a crafted deep document.
    return tree.css(tag + _PAGE_ELEMENT)


def titles(tree: LexborHTMLParser) -> list[str]:
    return [normalized(node.text()) for node in page_nodes(tree, "title")]


def meta_contents(metas: list[LexborNode], name: str) -> list[str]:
    return [
        normalized(node.attributes.get("content") or "") for node in metas if _is_named(node, name)
    ]


def meta_refresh(metas: list[LexborNode]) -> str | None:
    # http-equiv compared as 020 compares it for its meta_refresh Link: lowercased, not trimmed.
    for node in metas:
        if (node.attributes.get("http-equiv") or "").lower() == "refresh":
            return normalized(node.attributes.get("content") or "")
    return None


def declared_language(tree: LexborHTMLParser) -> str | None:
    attributes = {} if tree.root is None else tree.root.attributes
    if "lang" not in attributes:
        return None
    # <html lang> has the attribute with no value.
    return trimmed(attributes["lang"] or "")


def first_two(texts: list[str]) -> tuple[str | None, int | None, str | None, int | None]:
    first = texts[0] if texts else None
    second = texts[1] if len(texts) > 1 else None
    return first, _length(first), second, _length(second)


def _is_named(node: LexborNode, name: str) -> bool:
    value = trimmed(node.attributes.get("name") or "")
    # HTML compares attribute values ASCII case-insensitively, so a Kelvin sign is no k.
    return value.isascii() and value.lower() == name


def _length(text: str | None) -> int | None:
    return None if text is None else len(text)
