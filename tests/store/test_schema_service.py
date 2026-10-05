"""The schema service's order of tables (015-add-crawl-store, crawl-store)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Column, Integer, Table

from spider.services.schema import describe_schema
from spider.store.schema import metadata


@pytest.fixture
def table_of_an_earlier_change() -> Iterator[None]:
    """Declared after 015's tables, the way a later module would add its own."""
    table = Table(
        "earlier_rows",
        metadata,
        Column("n", Integer, primary_key=True, comment="A number."),
        comment="Rows of change 010.",
        info={"change": 10},
    )
    yield
    metadata.remove(table)


@pytest.mark.usefixtures("table_of_an_earlier_change")
def test_tables_are_ordered_by_the_adding_change_then_by_position() -> None:
    names = [table["name"] for table in describe_schema().tables]

    assert [name for name in names if name in {"earlier_rows", "crawl", "seeds"}] == [
        "earlier_rows",
        "crawl",
        "seeds",
    ]


@pytest.fixture
def internal_table() -> Iterator[None]:
    table = Table(
        "_writer_state",
        metadata,
        Column("n", Integer, primary_key=True, comment="A number."),
        comment="Internal rows of the tool.",
        info={"change": 15},
    )
    yield
    metadata.remove(table)


@pytest.mark.usefixtures("internal_table")
def test_tables_whose_names_start_with_an_underscore_are_internal() -> None:
    names = [table["name"] for table in describe_schema().tables]

    assert "_writer_state" not in names
