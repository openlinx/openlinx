"""The schema service behind `spider schema` (design D6 of 015-add-crawl-store)."""

from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects import sqlite

from spider.store.schema import metadata


def describe_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": table.name,
            "kind": "table",
            "description": table.comment,
            "columns": [_column(column) for column in table.columns],
        }
        for table in metadata.tables.values()
    ]


def _column(column: Column[Any]) -> dict[str, Any]:
    return {
        "name": column.name,
        "description": column.comment,
        "type": column.type.compile(dialect=sqlite.dialect()),
        "nullable": column.nullable,
        "primary_key": column.primary_key,
        "references": None,
        "format": None,
        "values": None,
    }
