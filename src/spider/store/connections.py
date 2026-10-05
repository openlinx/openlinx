"""Opening crawl files through URIs, one engine per operation (design D2 of 015-add-crawl-store)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import quote

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

READER_BUSY_SECONDS = 5.0
WRITER_BUSY_SECONDS = 30.0

# SQLite's primary result codes for a file or folder that cannot be written.
NOT_WRITABLE = {
    sqlite3.SQLITE_PERM,
    sqlite3.SQLITE_READONLY,
    sqlite3.SQLITE_IOERR,
    sqlite3.SQLITE_FULL,
    sqlite3.SQLITE_CANTOPEN,
}


def not_writable_name(error: BaseException) -> str | None:
    """SQLite's name for the error when it says a file cannot be written, otherwise None."""
    cause = error.orig if isinstance(error, DBAPIError) else error
    code = getattr(cause, "sqlite_errorcode", None)
    if code is None or code & 0xFF not in NOT_WRITABLE:
        return None
    return str(getattr(cause, "sqlite_errorname", code))


def is_busy(error: BaseException) -> bool:
    cause = error.orig if isinstance(error, DBAPIError) else error
    # Masked to the primary code, so BUSY_RECOVERY and BUSY_SNAPSHOT count too.
    code = getattr(cause, "sqlite_errorcode", None)
    return code is not None and code & 0xFF == sqlite3.SQLITE_BUSY


def file_uri(path: PurePath) -> str:
    posix = quote(path.as_posix(), safe="/:")
    # A UNC path keeps its host in the path (file:////host/share): SQLite refuses any URI
    # authority but localhost, which is why Path.as_uri() cannot be used.
    return f"file://{posix}" if posix.startswith("/") else f"file:///{posix}"


def connect(
    path: Path, *, read_only: bool = False, busy_seconds: float | None = None
) -> sqlite3.Connection:
    # rw, not SQLite's default rwc: a missing crawl file is an error, never a new empty file.
    uri = file_uri(path.resolve()) + ("?mode=ro" if read_only else "?mode=rw")
    # A reader gives up after 5 s (crawl_busy); the writer waits out a reader's longest wait.
    if busy_seconds is None:
        busy_seconds = READER_BUSY_SECONDS if read_only else WRITER_BUSY_SECONDS
    connection = sqlite3.connect(uri, uri=True, timeout=busy_seconds)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def opening(
    path: Path, *, read_only: bool = False, busy_seconds: float | None = None
) -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        creator=lambda: connect(path, read_only=read_only, busy_seconds=busy_seconds),
        poolclass=NullPool,
    )
    if not read_only:
        event.listen(engine, "connect", _own_transactions)
        event.listen(engine, "connect", _synchronous_for_the_journal)
        event.listen(engine, "begin", _begin_immediate)
    # Disposed at once, so no handle outlives the operation: Windows could not delete the file.
    try:
        yield engine
    finally:
        engine.dispose()


def _own_transactions(connection: sqlite3.Connection, _: Any) -> None:
    # pysqlite's implicit BEGIN would break SAVEPOINT; the begin event below issues ours.
    connection.isolation_level = None


def _synchronous_for_the_journal(connection: sqlite3.Connection, _: Any) -> None:
    (journal_mode,) = connection.execute("PRAGMA journal_mode").fetchone()
    # WAL stays durable at NORMAL; a rollback journal needs FULL for every commit.
    synchronous = "NORMAL" if journal_mode == "wal" else "FULL"
    connection.execute(f"PRAGMA synchronous = {synchronous}")


def _begin_immediate(connection: Connection) -> None:
    # IMMEDIATE takes the write lock at once, so a busy file fails at BEGIN, not mid-unit.
    connection.exec_driver_sql("BEGIN IMMEDIATE")
