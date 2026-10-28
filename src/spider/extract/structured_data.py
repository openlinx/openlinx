"""The structured-data counts and types of a Page's HTML (030-add-page-data D20)."""

from collections.abc import Iterator
from typing import Any

import orjson
from selectolax.lexbor import LexborHTMLParser

_JSON_LD = "application/ld+json"
_SCHEMA_ORG = ("http://schema.org/", "https://schema.org/")


def structured_data(tree: LexborHTMLParser) -> tuple[int, int, int, tuple[str, ...]]:
    """jsonld_items, microdata_items, jsonld_parse_errors and structured_data_types."""
    items: list[dict[str, Any]] = []
    errors = 0
    for script in tree.css("script"):
        if script.attributes.get("type") != _JSON_LD:
            continue
        try:
            # orjson stops at 1024 levels with a decode error, where json would raise
            # RecursionError and fail the whole Page extractor.
            items.extend(_items(orjson.loads(script.text())))
        except orjson.JSONDecodeError:
            errors += 1
    scopes = [node for node in tree.css("[itemscope]") if "itemprop" not in node.attributes]
    types = {
        _without_schema_org(item["@type"]) for item in items if isinstance(item.get("@type"), str)
    }
    types.update(
        _without_schema_org(node.attributes["itemtype"] or "")
        for node in scopes
        if "itemtype" in node.attributes
    )
    return len(items), len(scopes), errors, tuple(sorted(types))


def _items(value: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(value, dict):
        return
    graph = value.get("@graph")
    if isinstance(graph, list):
        yield from (item for item in graph if isinstance(item, dict))
    else:
        yield value


def _without_schema_org(name: str) -> str:
    for prefix in _SCHEMA_ORG:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name
