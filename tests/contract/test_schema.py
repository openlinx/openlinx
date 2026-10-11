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
from spider.services.schema_doc import parse_tables
from spider.store.schema import metadata
from spider.workspace.discovery import resolve_workspace
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, new_crawl
from tests.support.schema import indexed_rows_declared
from tests.support.workspace import TempWorkspace

SCHEMA_DOC = Path(__file__).resolve().parents[2] / "docs" / "schema.md"
CHECK_NAME = re.compile(r"CONSTRAINT (\w+) CHECK")


def test_documentation_and_declaration_agree() -> None:
    documented = parse_tables(SCHEMA_DOC.read_text(encoding="utf-8"))

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


INDEXED_SECTION = """## Table `urls`

The URLs.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `id` | INTEGER | no | PK | | | The URL id. |

### Indexes

| Name | Columns | Unique | Where | Description |
|---|---|---|---|---|
| `urls_crawl_depth_id` | `crawl_depth`, `id` | no | `fetch_state = 'queued'` | The frontier. |
| `urls_url` | `url` | yes | | Finds a URL. |
"""


def test_a_documented_indexes_table_is_parsed() -> None:
    assert parse_tables(INDEXED_SECTION) == [
        {
            "name": "urls",
            "kind": "table",
            "description": "The URLs.",
            "columns": [
                {
                    "name": "id",
                    "description": "The URL id.",
                    "type": "INTEGER",
                    "nullable": False,
                    "primary_key": True,
                    "references": None,
                    "format": None,
                    "values": None,
                }
            ],
            "indexes": [
                {
                    "name": "urls_crawl_depth_id",
                    "description": "The frontier.",
                    "columns": ["crawl_depth", "id"],
                    "unique": False,
                    "where": "fetch_state = 'queued'",
                },
                {
                    "name": "urls_url",
                    "description": "Finds a URL.",
                    "columns": ["url"],
                    "unique": True,
                    "where": None,
                },
            ],
        }
    ]
