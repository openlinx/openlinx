"""Tables follow the conventions (015-add-crawl-store, 018-add-schema-conventions, crawl-store)."""

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


def test_column_types_are_those_strict_allows() -> None:
    # Before any file is created: a Float column would declare FLOAT, which STRICT refuses.
    assert [
        column["name"]
        for column in all_columns()
        if column["type"] not in {"INTEGER", "REAL", "TEXT", "BLOB"}
    ] == []


def test_reference_columns_are_declared() -> None:
    # Vacuous until 020's found_on_url_id, whose task adds an assertion that one was seen.
    assert [
        column["name"]
        for column in all_columns()
        if column["name"].endswith("_id") and column["references"] is None
    ] == []


def test_index_names_start_with_their_table() -> None:
    # Vacuous until 020's urls_url, whose task adds an assertion that one was seen.
    assert [
        index["name"]
        for table in public_tables()
        for index in table["indexes"]
        if not index["name"].startswith(f"{table['name']}_")
        or not isinstance(index["description"], str)
        or not index["description"].strip()
    ] == []


LATER_OR_DERIVED = re.compile(r"Derived: |Filled from v[0-9]+\.[0-9]+\. ")


def test_derived_and_later_columns_may_hold_null() -> None:
    # Vacuous until 022's or 030's first later column, whose task adds an assertion one was seen.
    assert [
        column["name"]
        for column in all_columns()
        if LATER_OR_DERIVED.match(column["description"]) and not column["nullable"]
    ] == []
