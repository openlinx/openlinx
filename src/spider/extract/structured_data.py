"""The structured-data counts and types of a Page's HTML (030-add-page-data D20)."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import orjson
from selectolax.lexbor import LexborHTMLParser

from spider.extract.text import is_keyword, normalized

_JSON_LD = "application/ld+json"
_SCHEMA_ORG = ("http://schema.org/", "https://schema.org/")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredData:
    jsonld_items: int
    microdata_items: int
    jsonld_parse_errors: int
    structured_data_types: tuple[str, ...]


def structured_data(tree: LexborHTMLParser) -> StructuredData:
    items: list[dict[str, Any]] = []
    errors = 0
    for script in tree.css("script"):
        # Trimmed as HTML trims a script's type.
        if not is_keyword(script.attributes.get("type") or "", _JSON_LD):
            continue
        try:
            # orjson stops at 1024 levels with a decode error, where json would raise
            # RecursionError and fail the whole Page extractor.
            items.extend(_jsonld_items(orjson.loads(script.text())))
        except orjson.JSONDecodeError:
            errors += 1
    scopes = [node for node in tree.css("[itemscope]") if "itemprop" not in node.attributes]
    names = [name for item in items for name in _jsonld_types(item)]
    # itemtype is a set of tokens split at ASCII whitespace, which normalising makes one space.
    names += [
        name
        for node in scopes
        for name in normalized(node.attributes.get("itemtype") or "").split(" ")
    ]
    # Empty once the prefix is gone too: a template that had no type to put after it.
    types = {name for name in map(_without_schema_org, names) if name}
    return StructuredData(
        jsonld_items=len(items),
        microdata_items=len(scopes),
        jsonld_parse_errors=errors,
        structured_data_types=tuple(sorted(types)),
    )


def _jsonld_items(value: Any) -> Iterator[dict[str, Any]]:
    for entry in value if isinstance(value, list) else [value]:
        if not isinstance(entry, dict):
            continue
        graph = entry.get("@graph")
        if isinstance(graph, list):
            yield from (item for item in graph if isinstance(item, dict))
        elif isinstance(graph, dict):
            yield graph
        else:
            yield entry


def _jsonld_types(item: dict[str, Any]) -> list[str]:
    value = item.get("@type")
    return [
        name for name in (value if isinstance(value, list) else [value]) if isinstance(name, str)
    ]


def _without_schema_org(name: str) -> str:
    for prefix in _SCHEMA_ORG:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name
