"""Every public table follows the schema conventions (015-add-crawl-store, crawl-store)."""

import re
from typing import Any

from tests.support.cli import run_cli

SNAKE_CASE = re.compile(r"[a-z][a-z0-9_]*")


def public_tables() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = run_cli("schema", "--limit", "1000").json()["items"]
    return items


def test_names_are_snake_case() -> None:
    tables = public_tables()
    names = [table["name"] for table in tables] + [
        column["name"] for table in tables for column in table["columns"]
    ]

    assert [name for name in names if not SNAKE_CASE.fullmatch(name)] == []


def test_descriptions_are_present() -> None:
    tables = public_tables()
    descriptions = [table["description"] for table in tables] + [
        column["description"] for table in tables for column in table["columns"]
    ]

    assert [d for d in descriptions if not isinstance(d, str) or not d.strip()] == []


def all_columns() -> list[dict[str, Any]]:
    return [column for table in public_tables() for column in table["columns"]]


def test_booleans_are_integers() -> None:
    assert [
        column["name"]
        for column in all_columns()
        if column["format"] == "boolean" and column["type"] != "INTEGER"
    ] == []


def test_enumeration_values_are_snake_case() -> None:
    assert [
        value
        for column in all_columns()
        for value in column["values"] or []
        if not SNAKE_CASE.fullmatch(value)
    ] == []
