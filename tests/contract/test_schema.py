"""Docs, schema and file agree (015-add-crawl-store, 018-add-schema-conventions, crawl-store)."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.services.schema import describe_schema
from spider.store.schema import metadata
from spider.workspace.discovery import resolve_workspace
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, new_crawl
from tests.support.schema import indexed_rows_declared
from tests.support.workspace import TempWorkspace

SCHEMA_DOC = Path(__file__).resolve().parents[2] / "docs" / "schema.md"
SECTION = re.compile(r"^## (Table|View) `([^`]+)`$", re.MULTILINE)
REFERENCE = re.compile(r"→ `([^`]+)`")
CHECK_NAME = re.compile(r"CONSTRAINT (\w+) CHECK")


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
        "indexes": [],
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

    assert documented == run_cli("schema", "--limit", "1000").json()["items"]


def file_schema(file: Path) -> dict[str, dict[str, Any]]:
    """Public tables as SQLite reports them, in the shape of `declared_schema`."""
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        listed = {
            name: (without_rowid, strict)
            for schema, name, kind, _, without_rowid, strict in connection.execute(
                "PRAGMA table_list"
            )
            if schema == "main" and kind == "table" and not name.startswith(("sqlite_", "_"))
        }
        return {
            name: {
                "strict": bool(strict),
                "without_rowid": bool(without_rowid),
                "columns": _file_columns(connection, name),
                "indexes": _file_indexes(connection, name),
                "checks": sorted(CHECK_NAME.findall(_sql(connection, "table", name))),
            }
            for name, (without_rowid, strict) in listed.items()
        }


def _sql(connection: sqlite3.Connection, kind: str, name: str) -> str:
    query = "SELECT sql FROM sqlite_schema WHERE type = ? AND name = ?"
    sql: str = connection.execute(query, (kind, name)).fetchone()[0]
    return sql


def _file_columns(connection: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    references = {
        row[3]: f"{row[2]}.{row[4]}"
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }
    return [
        (column, type_, not notnull, pk > 0, references.get(column))
        for _, column, type_, notnull, _, pk in connection.execute(f"PRAGMA table_info({table})")
    ]


def _file_indexes(connection: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    indexes = []
    # origin "c" is an index made by CREATE INDEX; SQLite's own for keys have "pk" or "u".
    for _, name, unique, origin, partial in connection.execute(f"PRAGMA index_list({table})"):
        if origin != "c":
            continue
        columns = [
            column
            for _, _, column, _, _, key in connection.execute(f"PRAGMA index_xinfo({name})")
            if key
        ]
        where = _sql(connection, "index", name).split(" WHERE ", 1)[1] if partial else None
        indexes.append((name, columns, bool(unique), where))
    return sorted(indexes)


def declared_schema() -> dict[str, dict[str, Any]]:
    """The public tables of `spider schema`, with what only the declaration knows."""
    tables = {}
    for item in describe_schema().tables:
        table = metadata.tables[item["name"]]
        tables[item["name"]] = {
            "strict": True,
            "without_rowid": not table.dialect_options["sqlite"]["with_rowid"],
            "columns": [
                (
                    column["name"],
                    column["type"],
                    column["nullable"],
                    column["primary_key"],
                    column["references"],
                )
                for column in item["columns"]
            ],
            "indexes": [
                (index["name"], index["columns"], index["unique"], index["where"])
                for index in item["indexes"]
            ],
            "checks": sorted(
                str(constraint.name)
                for constraint in table.constraints
                if isinstance(constraint, CheckConstraint)
            ),
        }
    return tables


def test_a_new_file_matches_the_declaration(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider" / "crawls").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    file = create_crawl(new_crawl(workspace), FakeClock(), Collected()).path

    assert file_schema(file) == declared_schema()


def test_a_new_file_matches_a_declared_reference_and_indexes(
    temp_workspace: TempWorkspace,
) -> None:
    with indexed_rows_declared():
        file = create_any_crawl(temp_workspace).path

        assert file_schema(file) == declared_schema()


def test_every_table_is_strict(temp_workspace: TempWorkspace) -> None:
    file = create_any_crawl(temp_workspace).path
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        strict = {
            name: flag
            for schema, name, kind, _, _, flag in connection.execute("PRAGMA table_list")
            if schema == "main" and kind == "table" and not name.startswith(("sqlite_", "_"))
        }

    assert strict == {table["name"]: 1 for table in describe_schema().tables}
