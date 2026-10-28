"""The structured-data counts and types of a Page's HTML (030-add-page-data D20)."""

from collections.abc import Iterator
from typing import Any

import orjson
from selectolax.lexbor import LexborHTMLParser, LexborNode

from spider.extract.text import normalized, trimmed

_JSON_LD = "application/ld+json"
_SCHEMA_ORG = ("http://schema.org/", "https://schema.org/")


def structured_data(tree: LexborHTMLParser) -> tuple[int, int, int, tuple[str, ...]]:
    """jsonld_items, microdata_items, jsonld_parse_errors and structured_data_types."""
    items: list[dict[str, Any]] = []
    errors = 0
    for script in tree.css("script"):
        if not _is_json_ld(script):
            continue
        try:
            # orjson stops at 1024 levels with a decode error, where json would raise
            # RecursionError and fail the whole Page extractor.
            items.extend(_items(orjson.loads(script.text())))
        except orjson.JSONDecodeError:
            errors += 1
    scopes = [node for node in tree.css("[itemscope]") if "itemprop" not in node.attributes]
    names = [name for item in items for name in _jsonld_types(item)]
    # itemtype is a set of tokens split at ASCII whitespace, which normalising makes one space.
    names += [
        name
        for node in scopes
        for name in normalized(node.attributes.get("itemtype") or "").split(" ")
        if name
    ]
    types = {_without_schema_org(name) for name in names}
    return len(items), len(scopes), errors, tuple(sorted(types))


def _is_json_ld(script: LexborNode) -> bool:
    # Trimmed as HTML trims a script's type; compared ASCII case-insensitively, so a Kelvin
    # sign is no k.
    value = trimmed(script.attributes.get("type") or "")
    return value.isascii() and value.lower() == _JSON_LD


def _items(value: Any) -> Iterator[dict[str, Any]]:
    for node in value if isinstance(value, list) else [value]:
        if not isinstance(node, dict):
            continue
        graph = node.get("@graph")
        if isinstance(graph, list):
            yield from (item for item in graph if isinstance(item, dict))
        elif isinstance(graph, dict):
            yield graph
        else:
            yield node


def _jsonld_types(item: dict[str, Any]) -> list[str]:
    value = item.get("@type")
    values = value if isinstance(value, list) else [value]
    return [name for name in values if isinstance(name, str) and name]


def _without_schema_org(name: str) -> str:
    for prefix in _SCHEMA_ORG:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name
