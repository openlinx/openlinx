"""Evaluate the --where language on a test-defined SQLite table (seam 4)."""

from collections.abc import Iterator, Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import Column, Connection, Integer, MetaData, Table, Text, create_engine, select

from openlinx.output.diagnostics import OpenLinxError
from openlinx.query.where import Value, parse
from openlinx.store.query_where import compile_where
from openlinx.store.types import Flag

_PAGES = Table(
    "pages",
    MetaData(),
    Column("name", Text, primary_key=True),
    Column("status_code", Integer),
    Column("crawl_depth", Integer),
    Column("title_1", Text),
    Column("word_count", Integer),
    Column("flag", Flag),
)


@pytest.fixture
def connection() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as opened:
            _PAGES.create(opened)
            yield opened
    finally:
        engine.dispose()


def _matching(
    connection: Connection, where: str, pages: Mapping[str, Mapping[str, Value | None]]
) -> list[str]:
    connection.execute(
        _PAGES.insert(), [{"name": name, **values} for name, values in pages.items()]
    )
    query = select(_PAGES.c.name).where(compile_where(parse(where), _PAGES)).order_by(_PAGES.c.name)
    return list(connection.execute(query).scalars())


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("status_code >= 400", ["B", "C"]),
        ("status_code >= 404", ["B", "C"]),
        ("status_code = 404", ["B"]),
        ("status_code != 404", ["A", "C"]),
        ("status_code <> 404", ["A", "C"]),
        ("status_code < 404", ["A"]),
        ("status_code <= 404", ["A", "B"]),
        ("status_code > 404", ["C"]),
        ("status_code < 404.5", ["A", "B"]),
        ("status_code > -1", ["A", "B", "C"]),
    ],
)
def test_comparison(connection: Connection, where: str, expected: list[str]) -> None:
    pages = {"A": {"status_code": 200}, "B": {"status_code": 404}, "C": {"status_code": 500}}

    assert _matching(connection, where, pages) == expected


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("status_code = 404 and crawl_depth > 3", ["B"]),
        ("status_code = 404 AnD crawl_depth > 3", ["B"]),
        ("status_code = 404 and crawl_depth > 3 and crawl_depth < 5", []),
    ],
)
def test_and_requires_both(connection: Connection, where: str, expected: list[str]) -> None:
    pages = {
        "A": {"status_code": 404, "crawl_depth": 1},
        "B": {"status_code": 404, "crawl_depth": 5},
        "C": {"status_code": 200, "crawl_depth": 5},
    }

    assert _matching(connection, where, pages) == expected


def test_column_names_are_case_insensitive(connection: Connection) -> None:
    pages = {"A": {"status_code": 200}, "B": {"status_code": 404}}

    assert _matching(connection, "STATUS_CODE = 404", pages) == ["B"]


@pytest.mark.parametrize(
    ("where", "expected"),
    [("title_1 Is NuLl", ["A"]), ("title_1 IS NOT NULL", ["B"])],
)
def test_is_null_and_is_not_null(connection: Connection, where: str, expected: list[str]) -> None:
    pages: dict[str, dict[str, Value | None]] = {"A": {"title_1": None}, "B": {"title_1": "Hello"}}

    assert _matching(connection, where, pages) == expected


def test_doubled_quotes_inside_a_string(connection: Connection) -> None:
    pages = {"A": {"title_1": "It's here"}, "B": {"title_1": "Its here"}}

    assert _matching(connection, "title_1 = 'It''s here'", pages) == ["A"]


@pytest.mark.parametrize(
    ("title", "filter_text"),
    [("It's here", 'title_1 = "It\'s here"'), ('A "quote"', 'title_1 = "A ""quote"""')],
)
def test_double_quoted_string(connection: Connection, title: str, filter_text: str) -> None:
    pages = {"A": {"title_1": title}, "B": {"title_1": "Other"}}

    assert _matching(connection, filter_text, pages) == ["A"]


@pytest.mark.parametrize(
    ("where", "expected"),
    [("flag = true", ["A"]), ("flag = FaLsE", ["B"])],
)
def test_boolean_literal(connection: Connection, where: str, expected: list[str]) -> None:
    pages: dict[str, dict[str, Value | None]] = {
        "A": {"flag": True},
        "B": {"flag": False},
        "C": {"flag": None},
    }

    assert _matching(connection, where, pages) == expected


_WORD_COUNTS: dict[str, dict[str, Value | None]] = {
    "A": {"word_count": 250},
    "B": {"word_count": 800},
    "C": {"word_count": None},
}


def test_a_comparison_excludes_null_values(connection: Connection) -> None:
    assert _matching(connection, "word_count < 300", _WORD_COUNTS) == ["A"]

    predicate = compile_where(parse("word_count < 300"), _PAGES)
    evaluated = select(_PAGES.c.name, predicate.label("matches")).order_by(_PAGES.c.name)
    # The predicate itself is false for C. WHERE alone also drops SQL's unknown value.
    assert connection.execute(evaluated).all() == [("A", True), ("B", False), ("C", False)]


@pytest.mark.parametrize("comparison", ["!=", "<>"])
def test_not_equal_excludes_null_values(connection: Connection, comparison: str) -> None:
    assert _matching(connection, f"word_count {comparison} 250", _WORD_COUNTS) == ["B"]


# Grammar pieces exercise failures beyond the first token.
_WHERE_PIECES = st.sampled_from(
    [
        " ",
        "status_code",
        "title_1",
        " AND ",
        " contains ",
        " is not null",
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
    ]
)


@given(
    st.one_of(
        st.text(st.characters(exclude_categories=("C", "Zl", "Zp")), max_size=200),
        st.lists(_WHERE_PIECES, max_size=30).map(lambda pieces: "".join(pieces)[:200]),
    )
)
def test_any_input_either_parses_or_fails_cleanly(text: str) -> None:
    try:
        parse(text)
    except OpenLinxError as error:
        diagnostic = (error.code, error.exit_code)
    else:
        return

    assert diagnostic == ("invalid_where", 2)


@pytest.mark.parametrize(
    ("expression", "position"),
    [
        ("status_code = ", 15),
        ("title_1 = 'é' or title_1 = 'a'", 15),
        ("title_1 IS NOT TRUE", 16),
    ],
)
def test_invalid_where_names_the_character_position(expression: str, position: int) -> None:
    with pytest.raises(OpenLinxError) as caught:
        parse(expression)

    assert (caught.value.code, caught.value.exit_code) == ("invalid_where", 2)
    assert f"position {position}:" in caught.value.diagnostic.message
