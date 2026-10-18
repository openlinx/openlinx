"""The --where language on a table of its own (050-add-query-and-segments D1, D3; seam 4)."""

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
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

from spider.output.diagnostics import SpiderError
from spider.query.where import parse
from spider.store.query.where import compile_where, register_where_functions
from spider.store.types import Flag

ROWS = Table(
    "rows",
    MetaData(),
    Column("name", Text, primary_key=True),
    Column("status_code", Integer),
    Column("crawl_depth", Integer),
    Column("word_count", Integer),
    Column("title_1", Text),
    Column("meta_description_1", Text),
    # Declared as every boolean column of the schema is.
    Column("flag", Flag),
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
            # Not our fault: ruff takes the Russian title's Cyrillic O for a Latin look-alike.
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


def test_boolean_literal(connection: Connection) -> None:
    rows = {"A": {"flag": True}, "B": {"flag": False}}

    assert matching(connection, "flag = true", rows) == ["A"]


@pytest.mark.parametrize(
    ("where", "matched"),
    [
        ("status_code = 404 AND crawl_depth > 3", ["B"]),
        ("title_1 CONTAINS 'blog'", ["A"]),
        ("title_1 Is Not NULL", ["A", "B"]),
        ("flag = TRUE", ["A"]),
    ],
)
def test_keywords_of_v0_1_are_case_insensitive(
    connection: Connection, where: str, matched: list[str]
) -> None:
    rows: Rows = {
        "A": {"status_code": 200, "crawl_depth": 1, "title_1": "Blog", "flag": True},
        "B": {"status_code": 404, "crawl_depth": 5, "title_1": "Shop", "flag": False},
    }

    assert matching(connection, where, rows) == matched


WORD_COUNTS: Rows = {"A": {"word_count": 250}, "B": {"word_count": 800}, "C": {"word_count": None}}


def test_a_comparison_excludes_null_values(connection: Connection) -> None:
    assert matching(connection, "word_count < 300", WORD_COUNTS) == ["A"]


def test_not_equal_excludes_null_values(connection: Connection) -> None:
    assert matching(connection, "word_count != 250", WORD_COUNTS) == ["B"]


PRINTABLE = st.characters(exclude_categories=("C", "Zl", "Zp"))
# Pieces of the grammar, so that generated text gets past its first token.
GRAMMAR = st.sampled_from(
    [
        " ",
        "status_code",
        "AND",
        "and",
        "contains",
        "is",
        "not",
        "null",
        "true",
        "=",
        "!=",
        "<>",
        "<=",
        ">",
        "404",
        "-1.5",
        "'a''b'",
        '"x"',
        "'",
        '"',
        "(",
        ")",
        "~",
        ",",
        ";",
    ]
)


@given(
    st.one_of(
        st.text(PRINTABLE, max_size=200),
        st.lists(GRAMMAR, max_size=60).map(lambda pieces: "".join(pieces)[:200]),
    )
)
def test_any_input_either_parses_or_fails_cleanly(text: str) -> None:
    assert outcome(text) in {"parsed", "invalid_where"}


def outcome(text: str) -> str:
    try:
        parse(text)
    except SpiderError as error:
        return error.code
    return "parsed"


@pytest.mark.parametrize(
    "where",
    [
        "status_code = 404 or status_code = 500",
        "not status_code = 200",
        "(status_code = 200)",
        "address ~ '/blog/'",
        "address !~ '/blog/'",
        "status_code in (301, 404)",
        "status_code not in (301, 404)",
        "title_1 not contains 'blog'",
    ],
)
def test_the_operators_of_v0_2_are_syntax_errors(where: str) -> None:
    assert outcome(where) == "invalid_where"
