"""Docs, schema and file agree (015-add-crawl-store, 018-add-schema-conventions, crawl-store)."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint

from openlinx.output.reporter import Collected
from openlinx.services.crawls import create_crawl
from openlinx.services.schema import describe_schema
from openlinx.services.schema_doc import parse_tables
from openlinx.store.schema import metadata
from openlinx.workspace.discovery import resolve_workspace
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, new_crawl
from tests.support.schema import indexed_rows_declared
from tests.support.workspace import TempWorkspace

SCHEMA_DOC = Path(__file__).resolve().parents[2] / "docs" / "schema.md"
CHECK_NAME = re.compile(r"CONSTRAINT (\w+) CHECK")
IN_LIST = re.compile(r"\bIN \(([^)]*)\)")


def test_documentation_and_declaration_agree() -> None:
    documented = parse_tables(SCHEMA_DOC.read_text(encoding="utf-8"))

    assert documented == run_cli("schema", "--limit", "1000").json()["items"]


def test_no_check_lists_more_than_two_values(temp_workspace: TempWorkspace) -> None:
    """SQLite builds an ephemeral index for a longer IN list again on every executemany row."""
    crawl = create_any_crawl(temp_workspace)

    with closing(sqlite3.connect(f"{crawl.path.as_uri()}?mode=ro", uri=True)) as connection:
        tables = connection.execute("SELECT name, sql FROM sqlite_schema WHERE type = 'table'")
        long_lists = [
            (name, values)
            for name, sql in tables
            for values in IN_LIST.findall(sql or "")
            if values.count(",") > 1
        ]

    assert long_lists == [], (
        "a CHECK lists its values inline: build it with one_of(...) in openlinx.store.schema"
    )


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
                "checks": sorted(CHECK_NAME.findall(_create_sql(connection, "table", name))),
            }
            for name, (without_rowid, strict) in listed.items()
        }


def _create_sql(connection: sqlite3.Connection, kind: str, name: str) -> str:
    query = "SELECT sql FROM sqlite_schema WHERE type = ? AND name = ?"
    sql: str = connection.execute(query, (kind, name)).fetchone()[0]
    return sql


def _file_columns(connection: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    references = {
        column: f"{target}.{target_column}"
        for _, _, target, column, target_column, *_ in connection.execute(
            f"PRAGMA foreign_key_list({table})"
        )
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
        where = _create_sql(connection, "index", name).split(" WHERE ", 1)[1] if partial else None
        indexes.append((name, columns, bool(unique), where))
    return sorted(indexes)


def declared_schema() -> dict[str, dict[str, Any]]:
    """The public tables of `linx schema`, with what only the declaration knows.

    create_all makes CHECKs and WITHOUT ROWID from this declaration, so for those two the
    comparison guards against a file made another way, such as by a future migration.
    """
    tables = {}
    for item in describe_schema().tables:
        table = metadata.tables[item["name"]]
        tables[item["name"]] = {
            "strict": table.dialect_options["sqlite"]["strict"],
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
    (shop / ".openlinx" / "crawls").mkdir(parents=True)
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
    tables = file_schema(create_any_crawl(temp_workspace).path)

    assert {name: table["strict"] for name, table in tables.items()} == {
        table["name"]: True for table in describe_schema().tables
    }, "a table is not STRICT: declare it with public_table(...), which makes it STRICT"


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
