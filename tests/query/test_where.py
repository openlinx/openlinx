"""The --where language on a table of its own (050-add-query-and-segments, querying; seam 4)."""

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from sqlalchemy import (
    Column,
    Connection,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    insert,
    select,
)

from spider.query.where import parse
from spider.store.query.where import compile_where, register_where_functions

ROWS = Table(
    "rows",
    MetaData(),
    Column("name", Text, primary_key=True),
    Column("status_code", Integer),
    Column("crawl_depth", Integer),
    Column("title_1", Text),
    Column("meta_description_1", Text),
)

type Rows = Mapping[str, Mapping[str, Any]]


@pytest.fixture
def connection() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", register_where_functions)
    with engine.connect() as opened:
        ROWS.create(opened)
        yield opened
    engine.dispose()


def matching(connection: Connection, where: str, rows: Rows) -> list[str]:
    connection.execute(insert(ROWS), [{"name": name, **values} for name, values in rows.items()])
    chosen = select(ROWS.c.name).where(compile_where(parse(where), ROWS)).order_by(ROWS.c.name)
    return list(connection.execute(chosen).scalars())


def test_comparison(connection: Connection) -> None:
    rows = {"A": {"status_code": 200}, "B": {"status_code": 404}, "C": {"status_code": 500}}

    assert matching(connection, "status_code >= 400", rows) == ["B", "C"]


def test_and_requires_both(connection: Connection) -> None:
    rows = {
        "A": {"status_code": 404, "crawl_depth": 1},
        "B": {"status_code": 404, "crawl_depth": 5},
        "C": {"status_code": 200, "crawl_depth": 5},
    }

    assert matching(connection, "status_code = 404 and crawl_depth > 3", rows) == ["B"]


def test_column_names_are_case_insensitive(connection: Connection) -> None:
    rows = {"A": {"status_code": 200}, "B": {"status_code": 404}}

    assert matching(connection, "STATUS_CODE = 404", rows) == ["B"]


@pytest.mark.parametrize(
    ("rows", "where", "matched"),
    [
        (
            # The scenario's titles are Russian, so its O is Cyrillic.
            {"A": {"title_1": "Каталог товаров"}, "B": {"title_1": "О компании"}},  # noqa: RUF001
            "title_1 contains 'КАТАЛОГ'",
            ["A"],
        ),
        # Named after no scenario: contains reads any column as text.
        ({"A": {"status_code": 404}, "B": {"status_code": 311}}, "status_code contains '0'", ["A"]),
    ],
)
def test_contains_ignores_case_in_any_script(
    connection: Connection, rows: Rows, where: str, matched: list[str]
) -> None:
    assert matching(connection, where, rows) == matched


@pytest.mark.parametrize(
    ("where", "matched"),
    [("meta_description_1 is null", ["A"]), ("meta_description_1 is not null", ["B"])],
)
def test_is_null_and_is_not_null(connection: Connection, where: str, matched: list[str]) -> None:
    rows: Rows = {"A": {"meta_description_1": None}, "B": {"meta_description_1": "Hello"}}

    assert matching(connection, where, rows) == matched


@pytest.mark.parametrize("where", ["title_1 = 'It''s here'", 'title_1 = "It\'s here"'])
def test_doubled_quotes_inside_a_string_and_double_quoted_string(
    connection: Connection, where: str
) -> None:
    rows = {"A": {"title_1": "It's here"}, "B": {"title_1": "Its here"}}

    assert matching(connection, where, rows) == ["A"]
