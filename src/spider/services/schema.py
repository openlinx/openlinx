"""The service behind `spider schema` (015-add-crawl-store D6; 018-add-schema-conventions D4)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from spider.output.codes import UNKNOWN_TABLE
from spider.output.diagnostics import SpiderError

if TYPE_CHECKING:
    from sqlalchemy import Column, Index


@dataclass(frozen=True)
class SchemaDescription:
    schema_version: int
    tables: Sequence[dict[str, Any]]


def describe_schema(table: str | None = None) -> SchemaDescription:
    # Imported here: sqlalchemy stays off the CLI's startup path (design D9).
    from spider.store.schema import SCHEMA_VERSION, public_tables

    # sorted() is stable, so tables of one change keep the order the change declared them.
    declared = sorted(public_tables(), key=lambda candidate: candidate.info["change"])
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
            "kind": "view" if candidate.is_view else "table",
            "description": candidate.comment,
            "columns": [_column(column) for column in candidate.columns],
            # SQLite's own indexes for keys are not declared, so only secondary ones are listed.
            "indexes": [
                _index(index)
                for index in sorted(candidate.indexes, key=lambda index: index.name or "")
            ],
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
        # A view's column has no foreign key, so its declaration names the reference.
        "references": next(
            (key.target_fullname for key in column.foreign_keys),
            column.info.get("references"),
        ),
        "format": getattr(column.type, "format", None),
        "values": column.info.get("values"),
    }


def _index(index: "Index") -> dict[str, Any]:
    return {
        "name": index.name,
        "description": index.info.get("description"),
        "columns": [column.name for column in index.columns],
        "unique": index.unique,
        "where": _condition(index),
    }


def _condition(index: "Index") -> str | None:
    from sqlalchemy.dialects import sqlite

    where = index.dialect_options["sqlite"]["where"]
    if where is None:
        return None
    # As CREATE INDEX writes it: bare column names and literal values.
    options = {"include_table": False, "literal_binds": True}
    return str(where.compile(dialect=sqlite.dialect(), compile_kwargs=options))
