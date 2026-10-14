"""The pages table in spider schema (030-add-page-data, page-data; seam 6)."""

from tests.support.cli import run_cli


def test_indexes_of_pages() -> None:
    indexes = run_cli("schema", "pages", "--fields", "indexes").json()["items"][0]["indexes"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")} for index in indexes
    ]

    assert {"name": "pages_address", "columns": ["address"], "unique": True, "where": None} in (
        reduced
    )
