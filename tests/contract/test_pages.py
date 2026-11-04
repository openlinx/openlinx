"""The pages table in linx schema (030-add-page-data, page-data; seam 6)."""

from typing import Any

from tests.support.cli import run_cli
from tests.support.page_data import LATER_PAGE_COLUMNS


def test_indexes_of_pages() -> None:
    indexes = run_cli("schema", "pages", "--fields", "indexes").json()["items"][0]["indexes"]
    reduced = [
        {key: index[key] for key in ("name", "columns", "unique", "where")} for index in indexes
    ]

    assert {"name": "pages_address", "columns": ["address"], "unique": True, "where": None} in (
        reduced
    )


def test_inlink_columns_are_derived() -> None:
    columns = run_cli("schema", "pages").json()["items"][0]["columns"]
    descriptions = {column["name"]: column["description"] for column in columns}

    assert {
        name: descriptions[name][: len("Derived: ")]
        for name in ("inlinks", "unique_inlinks", "linking_pages_pct")
    } == dict.fromkeys(("inlinks", "unique_inlinks", "linking_pages_pct"), "Derived: ")


def _columns(table: str) -> dict[str, dict[str, Any]]:
    columns = run_cli("schema", table).json()["items"][0]["columns"]
    return {column["name"]: column for column in columns}


def test_deferred_columns_are_described_with_their_release() -> None:
    # Every later column, not only the spec's three, so a wrong release anywhere fails.
    pages, links = _columns("pages"), _columns("links")
    columns = {f"pages.{name}": pages.get(name) for name in LATER_PAGE_COLUMNS}
    columns["links.html_source"] = links.get("html_source")
    expected = {f"pages.{name}": f"Filled from {r}. " for name, r in LATER_PAGE_COLUMNS.items()}
    expected["links.html_source"] = "Filled from v1.1. "

    assert {
        key: column and column["description"][: len(expected[key])]
        for key, column in columns.items()
    } == expected


def test_structured_data_validation_counts_are_deferred_integer_columns() -> None:
    columns = _columns("pages")
    names = (
        "structured_data_error_count",
        "structured_data_warning_count",
        "structured_data_errors",
        "structured_data_warnings",
    )

    assert {
        name: (
            column["type"],
            column["nullable"],
            column["description"][: len("Filled from v0.3. ")],
        )
        for name in names
        if (column := columns.get(name)) is not None
    } == {
        "structured_data_error_count": ("INTEGER", True, "Filled from v0.3. "),
        "structured_data_warning_count": ("INTEGER", True, "Filled from v0.3. "),
    }


def test_later_enumerations_list_their_values() -> None:
    pages, links = _columns("pages"), _columns("links")

    assert (
        pages.get("readability", {}).get("values"),
        pages.get("http_version", {}).get("values"),
        links.get("html_source", {}).get("values"),
    ) == (
        [
            "very_easy",
            "easy",
            "fairly_easy",
            "normal",
            "fairly_difficult",
            "difficult",
            "very_difficult",
        ],
        ["http_2", "http_1_1"],
        ["raw", "rendered"],
    )
