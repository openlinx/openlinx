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
    insert,
    select,
)

from spider.query.where import parse
from spider.store.query.where import compile_where

ROWS = Table(
    "rows",
    MetaData(),
    Column("name", Text, primary_key=True),
    Column("status_code", Integer),
    Column("crawl_depth", Integer),
)


@pytest.fixture
def connection() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    with engine.connect() as opened:
        ROWS.create(opened)
        yield opened
    engine.dispose()


def matching(
    connection: Connection, where: str, rows: Mapping[str, Mapping[str, Any]]
) -> list[str]:
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
