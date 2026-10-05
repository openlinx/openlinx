"""`spider schema` (015-add-crawl-store, crawl-store)."""

from typing import Any

from tests.support.cli import run_cli


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
