"""`spider schema` (015-add-crawl-store, 018-add-schema-conventions, 022-add-fetch-policy,
crawl-store)."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.cli import run_cli
from tests.support.schema import indexed_rows_declared
from tests.support.workspace import TempWorkspace


def test_one_table() -> None:
    result = run_cli("schema", "seeds", "--fields", "name")

    assert (result.exit_code, result.stdout) == (
        0,
        b'{"schema_version":1,"total":1,"items":[{"name":"seeds"}],"next_cursor":null}\n',
    )


def test_first_tables() -> None:
    result = run_cli("schema", "--fields", "name,kind", "--limit", "2")

    assert result.json()["items"] == [
        {"name": "crawl", "kind": "table"},
        {"name": "seeds", "kind": "table"},
    ]


def test_columns_of_seeds() -> None:
    (item,) = run_cli("schema", "seeds").json()["items"]

    assert [
        {key: column[key] for key in ("name", "type", "nullable", "primary_key")}
        for column in item["columns"]
    ] == [
        {"name": "position", "type": "INTEGER", "nullable": False, "primary_key": True},
        {"name": "url", "type": "TEXT", "nullable": False, "primary_key": False},
    ]


def test_columns_of_response_headers() -> None:
    (item,) = run_cli("schema", "response_headers").json()["items"]

    assert (
        [
            {key: column[key] for key in ("name", "type", "nullable", "primary_key", "references")}
            for column in item["columns"]
        ],
        item["indexes"],
    ) == (
        [
            {
                "name": "url_id",
                "type": "INTEGER",
                "nullable": False,
                "primary_key": True,
                "references": "urls.id",
            },
            {
                "name": "headers",
                "type": "TEXT",
                "nullable": False,
                "primary_key": False,
                "references": None,
            },
        ],
        [],
    )


def columns_of(table: str) -> dict[str, dict[str, Any]]:
    (item,) = run_cli("schema", table).json()["items"]
    return {column["name"]: column for column in item["columns"]}


def test_the_http_version_is_a_later_column() -> None:
    column = columns_of("origins")["http_version"]

    assert (
        column["nullable"],
        column["values"],
        column["description"].startswith("Filled from v0.2. "),
    ) == (True, ["http_2", "http_1_1"], True)


def test_column_formats() -> None:
    columns = columns_of("crawl")

    assert [columns[name]["format"] for name in ("started_at", "section_crawl", "config")] == [
        "timestamp",
        "boolean",
        "json",
    ]


def test_state_values_are_documented() -> None:
    assert columns_of("crawl")["state"]["values"] == [
        "running",
        "stopped",
        "completed",
        "failed",
        "interrupted",
    ]


def test_the_next_page() -> None:
    first = run_cli("schema", "--fields", "name", "--limit", "1").json()

    second = run_cli(
        "schema", "--fields", "name", "--limit", "1", "--cursor", first["next_cursor"]
    ).json()

    assert second["items"] == [{"name": "seeds"}]


def test_unknown_table() -> None:
    result = run_cli("schema", "nosuch")
    error = result.stderr_json_lines()[-1]

    assert (
        result.exit_code,
        error["code"],
        {"crawl", "seeds"} <= set(error["details"]["tables"]),
    ) == (2, "unknown_table", True)


def test_internal_tables_are_hidden() -> None:
    items = run_cli("schema", "--fields", "name", "--limit", "1000").json()["items"]

    assert [item["name"] for item in items if item["name"].startswith("_")] == []


def test_no_workspace_needed(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    notes = temp_workspace.root / "notes"
    notes.mkdir()
    monkeypatch.chdir(notes)

    result = run_cli("schema")

    assert (result.exit_code, (temp_workspace.home / ".spider").exists()) == (0, False)


def test_a_table_without_secondary_indexes_lists_none() -> None:
    assert run_cli("schema", "seeds", "--fields", "name,indexes").json()["items"] == [
        {"name": "seeds", "indexes": []}
    ]


@pytest.fixture
def indexed_table() -> Iterator[None]:
    with indexed_rows_declared():
        yield


@pytest.mark.usefixtures("indexed_table")
def test_secondary_indexes_are_listed_in_name_order() -> None:
    assert run_cli("schema", "indexed_rows", "--fields", "indexes").json()["items"] == [
        {
            "indexes": [
                {
                    "name": "indexed_rows_state_id",
                    "description": "Lists queued rows in id order.",
                    "columns": ["state", "id"],
                    "unique": False,
                    "where": "state = 'queued'",
                },
                {
                    "name": "indexed_rows_url",
                    "description": "Finds a row by its URL.",
                    "columns": ["url"],
                    "unique": True,
                    "where": None,
                },
            ]
        }
    ]


def schema_entry() -> dict[str, Any]:
    entry: dict[str, Any] = next(
        command for command in run_cli("commands").json()["commands"] if command["name"] == "schema"
    )
    return entry


def test_self_description_of_schema() -> None:
    entry = schema_entry()

    assert (entry["output"], entry["formats"], entry["fields"]) == (
        "list",
        ["json", "jsonl", "table"],
        {
            "available": ["name", "kind", "description", "columns", "indexes"],
            "default": ["name", "kind", "description", "columns", "indexes"],
        },
    )


def test_global_flags_of_schema() -> None:
    names = {option["name"] for option in schema_entry()["options"]}

    assert ("--format" in names, "--workspace" in names, "--crawl" in names) == (True, False, False)


def test_default_limit_of_schema() -> None:
    limit = next(option for option in schema_entry()["options"] if option["name"] == "--limit")

    assert (limit["type"], limit["default"], limit["global"]) == ("integer", 50, False)


@pytest.mark.usefixtures("indexed_table")
def test_a_reference_names_its_target_column() -> None:
    assert columns_of("indexed_rows")["found_on_row_id"]["references"] == "indexed_rows.id"
