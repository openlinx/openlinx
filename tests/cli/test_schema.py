"""`spider schema` (015-add-crawl-store, crawl-store)."""

from typing import Any

import pytest

from tests.support.cli import run_cli
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


def columns_of(table: str) -> dict[str, dict[str, Any]]:
    (item,) = run_cli("schema", table).json()["items"]
    return {column["name"]: column for column in item["columns"]}


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
            "available": ["name", "kind", "description", "columns"],
            "default": ["name", "kind", "description", "columns"],
        },
    )
