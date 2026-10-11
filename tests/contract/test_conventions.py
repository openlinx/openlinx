"""Every public table follows the schema conventions (015-add-crawl-store, crawl-store)."""

import re
from typing import Any

from spider.store.schema import metadata
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

    assert [text for text in descriptions if not isinstance(text, str) or not text.strip()] == []


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


def test_every_declared_table_names_its_change_and_describes_itself() -> None:
    # Over the declaration, so a later table that forgets one fails here, not inside spider schema.
    missing = []
    for table in metadata.tables.values():
        if table.name.startswith("_"):
            continue
        if type(table.info.get("change")) is not int:
            missing.append(f"{table.name}: info change")
        if not table.comment:
            missing.append(f"{table.name}: comment")
        missing += [f"{table.name}.{c.name}: comment" for c in table.columns if not c.comment]

    assert missing == []
