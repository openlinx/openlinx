"""Tables follow the conventions (015-add-crawl-store, 018-add-schema-conventions, crawl-store)."""

import re
from typing import Any

from sqlalchemy import UniqueConstraint

from openlinx.store.schema import public_tables as declared_tables
from tests.support.cli import run_cli

SNAKE_CASE = re.compile(r"[a-z][a-z0-9_]*")
LATER_OR_DERIVED = re.compile(r"Derived: |Filled from v[0-9]+\.[0-9]+\. ")


def blank(text: Any) -> bool:
    return not isinstance(text, str) or not text.strip()


def listed_tables() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = run_cli("schema", "--limit", "1000").json()["items"]
    return items


def test_names_are_snake_case() -> None:
    tables = listed_tables()
    names = [table["name"] for table in tables] + [
        column["name"] for table in tables for column in table["columns"]
    ]

    assert [name for name in names if not SNAKE_CASE.fullmatch(name)] == [], (
        "a table or column name is not snake_case: rename it in openlinx.store.schema"
    )


def test_descriptions_are_present() -> None:
    tables = listed_tables()
    descriptions = [table["description"] for table in tables] + [
        column["description"] for table in tables for column in table["columns"]
    ]

    assert [text for text in descriptions if blank(text)] == [], (
        "a table or column has no description: give it a comment in openlinx.store.schema"
    )


def all_columns() -> list[dict[str, Any]]:
    return [column for table in listed_tables() for column in table["columns"]]


def test_booleans_are_integers() -> None:
    assert [
        column["name"]
        for column in all_columns()
        if column["format"] == "boolean" and column["type"] != "INTEGER"
    ] == [], "a boolean column is not INTEGER: declare it with the shared Boolean type"


def test_enumeration_values_are_snake_case() -> None:
    assert [
        value
        for column in all_columns()
        for value in column["values"] or []
        if not SNAKE_CASE.fullmatch(value)
    ] == [], "an enumeration value is not snake_case: rename it in its Literal"


def test_every_declared_table_names_its_change_and_describes_itself() -> None:
    # Over the declaration, so a later table that forgets one fails here, not inside linx schema.
    missing = []
    for table in declared_tables():
        if type(table.info.get("change")) is not int:
            missing.append(f"{table.name}: info change")
        if not table.comment:
            missing.append(f"{table.name}: comment")
        missing += [f"{table.name}.{c.name}: comment" for c in table.columns if not c.comment]

    assert missing == [], (
        "a declared table lacks its change or a comment: declare it with public_table(..., "
        "change=<n>) and a comment on the table and every column"
    )


def test_column_types_are_those_strict_allows() -> None:
    # Before any file is created: a Float column would declare FLOAT, which STRICT refuses.
    assert [
        column["name"]
        for column in all_columns()
        if column["type"] not in {"INTEGER", "REAL", "TEXT", "BLOB"}
    ] == [], "a column type is not one STRICT allows: use Integer, a REAL type, Text or a BLOB type"


def test_reference_columns_are_declared() -> None:
    references = [column for column in all_columns() if column["name"].endswith("_id")]

    # Seen at least once, so the rule is not passing vacuously.
    assert (
        [column["name"] for column in references if column["references"] is None],
        bool(references),
    ) == ([], True), "an _id column references nothing: give it its ForeignKey"


def test_index_names_start_with_their_table() -> None:
    indexes = [(table["name"], index) for table in listed_tables() for index in table["indexes"]]

    # Seen at least once, so the rule is not passing vacuously.
    assert (
        [
            index["name"]
            for table, index in indexes
            if not index["name"].startswith(f"{table}_") or blank(index["description"])
        ],
        bool(indexes),
    ) == ([], True), "an index is not <table>_... or lacks a description: rename or describe it"


def test_derived_and_later_columns_may_hold_null() -> None:
    # Vacuous until 022's or 030's first later column; its task asserts that one was seen.
    assert [
        column["name"]
        for column in all_columns()
        if LATER_OR_DERIVED.match(column["description"]) and not column["nullable"]
    ] == [], "a derived or later column is NOT NULL: let it hold NULL until it is filled"


def test_every_unique_rule_is_an_index_and_every_reference_one_key() -> None:
    # SQLite names a UNIQUE constraint's index itself, and linx schema lists only declared ones.
    problems = []
    for table in declared_tables():
        problems += [
            f"{table.name}: UNIQUE constraint on {', '.join(column.name for column in constraint)}"
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        # linx schema's references names one target, the first of a column's foreign keys.
        problems += [
            f"{table.name}.{column.name}: {len(column.foreign_keys)} foreign keys"
            for column in table.columns
            if len(column.foreign_keys) > 1
        ]

    assert problems == [], (
        "a UNIQUE rule is a constraint, or a column has two foreign keys: declare a unique Index, "
        "and one ForeignKey per column"
    )


def test_a_column_named_at_is_a_timestamp() -> None:
    assert [
        f"{table['name']}.{column['name']}"
        for table in listed_tables()
        for column in table["columns"]
        if column["name"].endswith("_at") and column["format"] != "timestamp"
    ] == [], (
        "a column whose name ends in _at is not a timestamp: declare it with the shared Timestamp "
        "type, or name it after what it holds"
    )


def test_a_message_column_explains_a_code_column() -> None:
    unexplained = []
    for table in listed_tables():
        values = {column["name"]: column["values"] for column in table["columns"]}
        for name in values:
            code = name.removesuffix("_message")
            if code != name and not values.get(code):
                unexplained.append(f"{table['name']}.{name}")

    assert unexplained == [], (
        "a column <x>_message has no column <x> with values: an error is a code column whose "
        "values are listed, beside the message column named after it"
    )
