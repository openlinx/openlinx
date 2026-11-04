"""The page_sources table in linx schema (030-add-page-data, page-data; seam 6)."""

from tests.support.cli import run_cli


def test_columns_of_page_sources() -> None:
    item = run_cli("schema", "page_sources").json()["items"][0]

    assert (
        {(column["name"], column["type"], column["nullable"]) for column in item["columns"]},
        item["description"][: len("Filled from v0.2. ")],
    ) == (
        {("url_id", "INTEGER", False), ("encoding", "TEXT", False), ("html", "BLOB", False)},
        "Filled from v0.2. ",
    )
