"""Exercise SQL reads through the selected Crawl's Store boundary."""

import json
import sqlite3
from contextlib import closing
from functools import partial
from itertools import chain, repeat
from pathlib import Path

import pytest

from openlinx.json_numbers import encode_json
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.sql import sql_document
from openlinx.store.connections import connect
from openlinx.store.identity import identify_file
from openlinx.store.records import JournalSetting
from openlinx.store.selection import resolve_crawl
from openlinx.store.sql import read_sql
from tests.support.crawl_store import crawl_store
from tests.support.crawls import create_any_crawl, current_workspace, query, sha256_of
from tests.support.workspace import TempWorkspace


def test_a_select_runs(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, "SELECT 1 AS one")

    assert result.columns == ("one",)
    assert result.rows == ((1,),)
    assert json.loads(encode_json(sql_document(result))) == {
        "columns": ["one"],
        "rows": [[1]],
        "row_count": 1,
        "truncated": False,
        "limit": 1000,
    }


def test_duplicate_column_names(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, "SELECT 1 AS a, 2 AS a")
    document = json.loads(encode_json(sql_document(result)))

    assert document["columns"] == ["a", "a"]
    assert document["rows"] == [[1, 2]]


def test_blob_values(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, "SELECT x'00010203' AS b")
    document = json.loads(encode_json(sql_document(result)))

    assert result.rows == ((b"\x00\x01\x02\x03",),)
    assert document["rows"] == [[{"blob_bytes": 4}]]


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_sql_reads_the_selected_crawl(
    temp_workspace: TempWorkspace, journal: JournalSetting
) -> None:
    first = create_any_crawl(
        temp_workspace, journal_setting=journal, seeds=["https://example.com/first"]
    )
    second = create_any_crawl(
        temp_workspace, journal_setting=journal, seeds=["https://example.com/second"]
    )
    workspace = current_workspace(temp_workspace)
    chosen = resolve_crawl(first.id, workspace=workspace, cwd=temp_workspace.root)
    other = resolve_crawl(second.id, workspace=workspace, cwd=temp_workspace.root)
    before = sha256_of(chosen.path)
    statement = "SELECT url FROM seeds"

    assert read_sql(chosen, statement).rows == (("https://example.com/first",),)
    assert read_sql(other, statement).rows == (("https://example.com/second",),)
    assert sha256_of(chosen.path) == before

    # SQLite backup replaces the contents of the existing file after selection has closed it.
    with (
        closing(sqlite3.connect(other.path)) as source,
        closing(sqlite3.connect(chosen.path)) as target,
    ):
        source.backup(target)

    assert identify_file(chosen.path) == chosen.identity
    assert query(chosen.path, "SELECT id FROM crawl") == [(other.id,)]
    assert query(chosen.path, "PRAGMA journal_mode") == [(journal,)]
    replaced = sha256_of(chosen.path)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(chosen, statement)

    assert (raised.value.code, raised.value.exit_code, raised.value.diagnostic.details) == (
        "crawl_file_invalid",
        6,
        {"file": str(chosen.path), "expected_id": first.id, "found_id": second.id},
    )
    assert sha256_of(chosen.path) == replaced


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM pages",
        "-- read the Crawl\n/* SELECT */ DELETE FROM pages",
        "CREATE TEMP TABLE notes (value INTEGER)",
        "SELECTED",
    ],
    ids=["delete", "commented-delete", "temp-schema", "keyword-prefix"],
)
def test_writes_are_refused(temp_workspace: TempWorkspace, statement: str) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, statement)

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)


def test_two_statements_are_refused(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT 1; SELECT 2")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert read_sql(crawl, "SELECT ';' AS value; -- trailing comment\n").rows == ((";",),)


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_multiple_statements_are_refused_before_sqlite_resolves_names(
    temp_workspace: TempWorkspace, journal: JournalSetting
) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting=journal)
    before = sha256_of(crawl.path)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT no_such_column FROM crawl; /* between statements */ SELECT 2")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert sha256_of(crawl.path) == before


def test_semicolons_in_quoted_tokens_and_comments(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    statement = '''
        SELECT 'it''s; a value' AS "one; ""a""", 2 AS [two; b], 3 AS `three; ``c```
        -- ; inside this line
        ; /* ; after the statement */
    '''

    result = read_sql(crawl, statement)

    assert result.columns == ('one; "a"', "two; b", "three; `c`")
    assert result.rows == (("it's; a value", 2, 3),)


def test_pragma_is_refused(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting="wal")

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "PRAGMA journal_mode=DELETE")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert query(crawl.path, "PRAGMA journal_mode") == [("wal",)]


def test_a_with_that_writes_is_refused(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "WITH x AS (SELECT 1) DELETE FROM pages")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert read_sql(crawl, "WITH x AS (SELECT 1) SELECT * FROM x").rows == ((1,),)


def test_attach_is_refused(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    destination = temp_workspace.root / "other.db"
    quoted_path = destination.as_posix().replace("'", "''")
    files_before = set(temp_workspace.root.iterdir())

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, f"ATTACH DATABASE '{quoted_path}' AS other")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert not destination.exists()
    assert set(temp_workspace.root.iterdir()) == files_before


def test_loading_an_extension_is_refused(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT load_extension('unused')")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert read_sql(crawl, "SELECT lower('A')").rows == (("a",),)


def _crawl_dump(path: Path) -> tuple[str, ...]:
    with closing(connect(path, read_only=True)) as connection:
        return tuple(connection.iterdump())


@pytest.mark.parametrize("journal", ["wal", "delete"])
def test_a_refused_write_changes_nothing(
    temp_workspace: TempWorkspace, journal: JournalSetting
) -> None:
    path = crawl_store(
        temp_workspace,
        pages={"https://example.com/report": "<title>Report</title>"},
        journal_setting=journal,
    )
    crawl = resolve_crawl(
        str(path), workspace=current_workspace(temp_workspace), cwd=temp_workspace.root
    )
    assert query(path, "SELECT address FROM pages ORDER BY address") == [
        ("https://example.com/",),
        ("https://example.com/report",),
    ]
    before = _crawl_dump(path)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "DELETE FROM pages")

    assert (raised.value.code, raised.value.exit_code) == ("sql_not_allowed", 2)
    assert _crawl_dump(path) == before


@pytest.mark.parametrize(
    "statement",
    [
        " \t/* A report */\r\n-- The count\n SeLeCt/* label */1 AS one",
        "-- A report\n/* The count */ WiTh n(i) AS (SELECT 1) SELECT i AS one FROM n",
    ],
    ids=["select", "with"],
)
def test_sql_reader_accepts_leading_comments(temp_workspace: TempWorkspace, statement: str) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, statement)

    assert (result.columns, result.rows) == (("one",), ((1,),))


_NUMBERED_ROWS = (
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 1500) "
    "SELECT i FROM n ORDER BY i"
)


def test_default_row_limit(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, _NUMBERED_ROWS)

    assert json.loads(encode_json(sql_document(result))) == {
        "columns": ["i"],
        "rows": [[i] for i in range(1, 1001)],
        "row_count": 1000,
        "truncated": True,
        "limit": 1000,
    }


def test_custom_row_limit(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)

    result = read_sql(crawl, _NUMBERED_ROWS, limit=5)

    assert json.loads(encode_json(sql_document(result))) == {
        "columns": ["i"],
        "rows": [[1], [2], [3], [4], [5]],
        "row_count": 5,
        "truncated": True,
        "limit": 5,
    }

    fits = read_sql(crawl, "SELECT 1 AS i UNION ALL SELECT 2", limit=2)
    assert (fits.rows, fits.row_count, fits.truncated, fits.limit) == (((1,), (2,)), 2, False, 2)


@pytest.mark.parametrize("limit", [0, 100_001])
def test_row_limit_out_of_bounds(temp_workspace: TempWorkspace, limit: int) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT 1", limit=limit)

    assert (raised.value.code, raised.value.exit_code) == ("invalid_value", 2)


@pytest.mark.parametrize("timeout", [None, 1.0], ids=["default", "explicit"])
def test_timeout(temp_workspace: TempWorkspace, timeout: float | None) -> None:
    crawl = create_any_crawl(temp_workspace)
    deadline = 30.0 if timeout is None else timeout
    # The first SQLite progress check is within budget. The next crosses the deadline.
    ticks = chain((100.0, 100.0 + deadline - 0.5), repeat(100.0 + deadline + 0.5))

    if timeout is None:
        read = partial(read_sql, crawl, _NUMBERED_ROWS, monotonic=ticks.__next__)
    else:
        stream = _NUMBERED_ROWS.removesuffix(" ORDER BY i")
        read = partial(read_sql, crawl, stream, timeout=timeout, monotonic=ticks.__next__)
    with pytest.raises(OpenLinxError) as raised:
        read()

    assert (raised.value.code, raised.value.exit_code) == ("sql_timeout", 1)
    assert read_sql(crawl, "SELECT 1").rows == ((1,),)


def test_a_short_query_can_exceed_the_timeout(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    ticks = chain((100.0,), repeat(101.5))

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT 1", timeout=1.0, monotonic=ticks.__next__)

    assert (raised.value.code, raised.value.exit_code) == ("sql_timeout", 1)
    assert read_sql(crawl, "SELECT 1", timeout=1.0, monotonic=lambda: 100.0).rows == ((1,),)


@pytest.mark.parametrize(
    "timeout", [-1.0, float("inf"), float("nan")], ids=["negative", "inf", "nan"]
)
def test_timeout_out_of_bounds(temp_workspace: TempWorkspace, timeout: float) -> None:
    crawl = create_any_crawl(temp_workspace)

    with pytest.raises(OpenLinxError) as raised:
        read_sql(crawl, "SELECT 1", timeout=timeout)

    assert (raised.value.code, raised.value.exit_code) == ("invalid_value", 2)
