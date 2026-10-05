"""`spider schema` (015-add-crawl-store, crawl-store)."""

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
