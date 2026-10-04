"""The documented and the declared schema agree (015-add-crawl-store, crawl-store)."""

import re
from pathlib import Path
from typing import Any

from spider.services.schema import describe_schema

SCHEMA_DOC = Path(__file__).resolve().parents[2] / "docs" / "schema.md"
SECTION = re.compile(r"^## (Table|View) `([^`]+)`$", re.MULTILINE)
REFERENCE = re.compile(r"→ `([^`]+)`")


def documented_schema(markdown: str) -> list[dict[str, Any]]:
    """`## Table` sections: a description paragraph, then a pipe-table row per column."""
    headings = list(SECTION.finditer(markdown))
    ends = [heading.start() for heading in headings] + [len(markdown)]
    return [
        _table(heading.group(1).lower(), heading.group(2), markdown[heading.end() : end])
        for heading, end in zip(headings, ends[1:], strict=True)
    ]


def _table(kind: str, name: str, body: str) -> dict[str, Any]:
    lines = [line.strip() for line in body.strip().splitlines()]
    paragraph = [line for line in lines if line and not line.startswith(("|", "#"))]
    rows = [line for line in lines if line.startswith("|")][2:]
    return {
        "name": name,
        "kind": kind,
        "description": " ".join(paragraph),
        "columns": [_column(row) for row in rows],
    }


def _column(row: str) -> dict[str, Any]:
    name, type_, null, key, format_, values, description = (
        cell.strip() for cell in row.strip("|").split("|")
    )
    reference = REFERENCE.search(key)
    return {
        "name": name.strip("`"),
        "description": description,
        "type": type_,
        "nullable": null == "yes",
        "primary_key": "PK" in key,
        "references": reference.group(1) if reference else None,
        "format": format_.strip("`") or None,
        "values": [value.strip().strip("`") for value in values.split(",")] if values else None,
    }


def test_documentation_and_declaration_agree() -> None:
    documented = documented_schema(SCHEMA_DOC.read_text(encoding="utf-8"))

    assert documented == describe_schema()
