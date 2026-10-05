"""The schema service behind `spider schema` (design D6 of 015-add-crawl-store)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from spider.output.codes import UNKNOWN_TABLE
from spider.output.diagnostics import SpiderError

if TYPE_CHECKING:
    from sqlalchemy import Column


@dataclass(frozen=True)
class SchemaDescription:
    schema_version: int
    tables: Sequence[dict[str, Any]]


def describe_schema(table: str | None = None) -> SchemaDescription:
    # Imported here: sqlalchemy stays off the CLI's startup path (design D9).
    from spider.store.schema import SCHEMA_VERSION, metadata

    # sorted() is stable, so tables of one change keep the order the change declared them.
    declared = sorted(metadata.tables.values(), key=lambda candidate: candidate.info["change"])
    names = [candidate.name for candidate in declared]
    if table is not None and table not in names:
        raise SpiderError(
            UNKNOWN_TABLE,
            f"The schema has no table {table}.",
            hint=f"Use one of: {', '.join(names)}.",
            details={"tables": names},
        )
    tables = [
        {
            "name": candidate.name,
            "kind": "table",
            "description": candidate.comment,
            "columns": [_column(column) for column in candidate.columns],
        }
        for candidate in declared
        if table is None or candidate.name == table
    ]
    return SchemaDescription(SCHEMA_VERSION, tables)


def _column(column: "Column[Any]") -> dict[str, Any]:
    from sqlalchemy.dialects import sqlite

    return {
        "name": column.name,
        "description": column.comment,
        "type": column.type.compile(dialect=sqlite.dialect()),
        "nullable": column.nullable,
        "primary_key": column.primary_key,
        "references": None,
        "format": getattr(column.type, "format", None),
        "values": column.info.get("values"),
    }
