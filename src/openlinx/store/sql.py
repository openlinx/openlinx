"""Run SQL on the selected Crawl's read-only snapshot."""

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from difflib import get_close_matches
from math import inf
from time import monotonic as system_monotonic
from typing import cast

from sqlalchemy.exc import DBAPIError

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import INVALID_VALUE, SQL_ERROR, SQL_NOT_ALLOWED, SQL_TIMEOUT
from openlinx.output.diagnostics import OpenLinxError
from openlinx.query.sql import DEFAULT_SQL_LIMIT, DEFAULT_SQL_TIMEOUT, MAX_SQL_LIMIT
from openlinx.store.connections import is_busy
from openlinx.store.reading import reading_selected
from openlinx.store.records import CrawlFile
from openlinx.store.schema import public_tables

_PROGRESS_STEPS = 1_000
_LEADING_TRIVIA = re.compile(r"[ \t\n\r\f\ufeff]+|--[^\n]*|/\*.*?(?:\*/|\Z)", re.DOTALL)
# SQLite permits non-ASCII characters and dollar signs inside unquoted identifiers.
_IDENTIFIER_CHAR = r"[\w$\x80-\U0010ffff]"
_READ_START = re.compile(rf"(?:SELECT|WITH)(?!{_IDENTIFIER_CHAR})", re.IGNORECASE | re.ASCII)
# Comments, quoted tokens and named parameter suffixes can contain literal semicolons.
_STATEMENT_TOKENS = re.compile(
    rf"""{_LEADING_TRIVIA.pattern}|'(?:[^']|'')*+(?:'|\Z)|"(?:[^"]|"")*+(?:"|\Z)"""
    rf"""|`(?:[^`]|``)*+(?:`|\Z)|\[[^\]]*+(?:\]|\Z)"""
    rf"""|[$:@#](?:{_IDENTIFIER_CHAR}|::)++\([^)\x00 \t\n\r\f]*+\)"""
    rf"""|{_IDENTIFIER_CHAR}++|;""",
    re.DOTALL | re.ASCII,
)
_READ_ACTIONS = frozenset({sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE})
# CPython rejects a second statement before stepping the first, without a SQLite error code.
_MULTIPLE_STATEMENTS = "You can only execute one statement at a time."
_MISSING_LOAD_EXTENSION = "no such function: load_extension"


@dataclass(frozen=True, kw_only=True)
class SqlResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[int | float | str | bytes | None, ...], ...]
    row_count: int
    truncated: bool
    limit: int


def _skip_trivia(statement: str, start: int) -> int:
    while (trivia := _LEADING_TRIVIA.match(statement, start)) is not None:
        start = trivia.end()
    return start


def _check_statement(statement: str) -> None:
    start = _skip_trivia(statement, 0)
    if _READ_START.match(statement, start) is None:
        raise OpenLinxError(
            SQL_NOT_ALLOWED, "A read-only SQL statement must start with SELECT or WITH."
        )
    if ";" not in statement:
        return
    # SQLite can fail to prepare the first statement before its driver checks the tail.
    for token in _STATEMENT_TOKENS.finditer(statement, start):
        if token[0] == ";":
            if _skip_trivia(statement, token.end()) < len(statement):
                raise OpenLinxError(SQL_NOT_ALLOWED, "SQL accepts only one statement.")
            return


def _authorize_read(action: int, detail: str | None) -> int:
    if action in _READ_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and detail is not None:
        return sqlite3.SQLITE_DENY if detail.casefold() == "load_extension" else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _timeout_error(timeout: float) -> OpenLinxError:
    return OpenLinxError(SQL_TIMEOUT, f"SQL exceeded its {timeout:g}-second time limit.")


def _query_error(error: sqlite3.Error) -> OpenLinxError:
    message = str(error)
    kind, _, unknown = message.partition(": ")
    if kind == "no such table":
        names = {str(table.name) for table in public_tables()}
    elif kind == "no such column":
        names = {str(column.name) for table in public_tables() for column in table.columns}
    else:
        return OpenLinxError(SQL_ERROR, message)
    return OpenLinxError(
        SQL_ERROR,
        message,
        hint=f"Use {COMMAND_NAME} schema to look up table and column names.",
        details={"suggestions": get_close_matches(unknown.rsplit(".", 1)[-1].casefold(), names)},
    )


def read_sql(
    selected: CrawlFile,
    statement: str,
    *,
    limit: int = DEFAULT_SQL_LIMIT,
    timeout: float = DEFAULT_SQL_TIMEOUT,
    monotonic: Callable[[], float] = system_monotonic,
) -> SqlResult:
    """Read a bounded result in column order, with native SQLite values for the caller."""
    if not 1 <= limit <= MAX_SQL_LIMIT:
        raise OpenLinxError(
            INVALID_VALUE, f"SQL result limit must be between 1 and {MAX_SQL_LIMIT}."
        )
    if not 0 <= timeout < inf:
        raise OpenLinxError(INVALID_VALUE, "SQL timeout must be finite and nonnegative.")
    denied = False

    def authorize(
        action: int,
        _object: str | None,
        detail: str | None,
        _database: str | None,
        _source: str | None,
    ) -> int:
        nonlocal denied
        decision = _authorize_read(action, detail)
        denied = denied or decision == sqlite3.SQLITE_DENY
        return decision

    with reading_selected(selected) as connection:
        _check_statement(statement)
        driver = cast(sqlite3.Connection, connection.connection.driver_connection)
        deadline = monotonic() + timeout

        def expired() -> bool:
            return monotonic() >= deadline

        # Read-only mode protects the Crawl file. The authorizer also protects TEMP and ATTACH.
        driver.set_authorizer(authorize)
        try:
            driver.set_progress_handler(expired, _PROGRESS_STEPS)
            with connection.exec_driver_sql(statement) as result:
                columns = tuple(result.keys())
                batch = result.fetchmany(limit + 1)
            # A short statement can finish between SQLite progress checks.
            if expired():
                raise _timeout_error(timeout)
        except DBAPIError as error:
            cause = error.orig
            if not isinstance(cause, sqlite3.Error) or is_busy(error):
                raise
            if getattr(cause, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                raise _timeout_error(timeout) from error
            # SQLite builds without extension loading cannot authorize an absent function.
            if denied or str(cause).casefold() == _MISSING_LOAD_EXTENSION:
                raise OpenLinxError(SQL_NOT_ALLOWED, "SQL may only read the Crawl.") from error
            if isinstance(cause, sqlite3.ProgrammingError) and str(cause) == _MULTIPLE_STATEMENTS:
                raise OpenLinxError(SQL_NOT_ALLOWED, "SQL accepts only one statement.") from error
            raise _query_error(cause) from error
        finally:
            driver.set_progress_handler(None, 0)
            driver.set_authorizer(None)

    rows = tuple(tuple(row) for row in batch[:limit])
    return SqlResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(batch) > limit,
        limit=limit,
    )
