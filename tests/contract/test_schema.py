"""Docs, schema and file agree (015-add-crawl-store, 018-add-schema-conventions, crawl-store)."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.services.schema import describe_schema
from spider.workspace.discovery import resolve_workspace
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, new_crawl
from tests.support.workspace import TempWorkspace

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


def file_schema(file: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Public tables as SQLite reports them: (name, type, nullable, primary key, reference)."""
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        names = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
            )
            if not name.startswith(("sqlite_", "_"))
        ]
        tables = {}
        for name in names:
            references = {
                row[3]: f"{row[2]}.{row[4]}"
                for row in connection.execute(f"PRAGMA foreign_key_list({name})")
            }
            tables[name] = [
                (column, type_, not notnull, pk > 0, references.get(column))
                for _, column, type_, notnull, _, pk in connection.execute(
                    f"PRAGMA table_info({name})"
                )
            ]
    return tables


def test_a_new_file_matches_the_declaration(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".spider" / "crawls").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)
    file = create_crawl(new_crawl(workspace), FakeClock(), Collected()).path

    declared = {
        table["name"]: [
            (
                column["name"],
                column["type"],
                column["nullable"],
                column["primary_key"],
                column["references"],
            )
            for column in table["columns"]
        ]
        for table in describe_schema().tables
    }

    assert file_schema(file) == declared


def test_every_table_is_strict(temp_workspace: TempWorkspace) -> None:
    file = create_any_crawl(temp_workspace).path
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        strict = {
            name: flag
            for schema, name, kind, _, _, flag in connection.execute("PRAGMA table_list")
            if schema == "main" and kind == "table" and not name.startswith(("sqlite_", "_"))
        }

    assert strict == {table["name"]: 1 for table in describe_schema().tables}
