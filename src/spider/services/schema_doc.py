"""Reading the table sections of the schema reference (018-add-schema-conventions D4)."""

import re
from typing import Any

_SECTION = re.compile(r"^## (Table|View) `([^`]+)`$", re.MULTILINE)
_REFERENCE = re.compile(r"→ `([^`]+)`")
_INDEXES = "### Indexes"


def parse_tables(text: str) -> list[dict[str, Any]]:
    """`## Table` sections: a description, a row per column, then any `### Indexes` table."""
    headings = list(_SECTION.finditer(text))
    ends = [heading.start() for heading in headings] + [len(text)]
    return [
        _table(heading.group(1).lower(), heading.group(2), text[heading.end() : end])
        for heading, end in zip(headings, ends[1:], strict=True)
    ]


def _table(kind: str, name: str, body: str) -> dict[str, Any]:
    head, _, indexes = body.partition(_INDEXES)
    lines = _lines(head)
    paragraph = [line for line in lines if line and not line.startswith(("|", "#"))]
    return {
        "name": name,
        "kind": kind,
        "description": " ".join(paragraph),
        "columns": [_column(row) for row in _rows(lines)],
        "indexes": [_index(row) for row in _rows(_lines(indexes))],
    }


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines()]


def _rows(lines: list[str]) -> list[list[str]]:
    """A pipe table's cells, row by row, without its heading and separator rows."""
    rows = [line for line in lines if line.startswith("|")][2:]
    return [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]


def _names(cell: str) -> list[str]:
    return [name.strip().strip("`") for name in cell.split(",")]


def _code(cell: str) -> str | None:
    return cell.strip("`") or None


def _column(row: list[str]) -> dict[str, Any]:
    name, type_, null, key, format_, values, description = row
    reference = _REFERENCE.search(key)
    return {
        "name": name.strip("`"),
        "description": description,
        "type": type_,
        "nullable": null == "yes",
        "primary_key": "PK" in key,
        "references": reference.group(1) if reference else None,
        "format": _code(format_),
        "values": _names(values) if values else None,
    }


def _index(row: list[str]) -> dict[str, Any]:
    name, columns, unique, where, description = row
    return {
        "name": name.strip("`"),
        "description": description,
        "columns": _names(columns),
        "unique": unique == "yes",
        "where": _code(where),
    }
