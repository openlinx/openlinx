"""One engine per crawl-file operation (015-add-crawl-store D2; 017-speed-up-crawl-writer D8)."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Any, Literal
from urllib.parse import quote

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from spider.output.codes import CRAWL_BUSY
from spider.output.diagnostics import SpiderError

READER_BUSY_SECONDS = 5.0
WRITER_BUSY_SECONDS = 30.0
# How often opening looks again at a -shm file that a killed writer still holds.
SHM_RELEASE_CHECK_SECONDS = 0.05

WRITER_CACHE_KIB = 65_536
WRITER_MMAP_BYTES = 268_435_456

type ConnectionRole = Literal["create", "read", "write"]

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
    cause, code = _sqlite_code(error)
    if code is None or code & 0xFF not in NOT_WRITABLE:
        return None
    return str(getattr(cause, "sqlite_errorname", code))


def is_busy(error: BaseException) -> bool:
    _, code = _sqlite_code(error)
    # Masked to the primary code, so BUSY_RECOVERY and BUSY_SNAPSHOT count too.
    return code is not None and code & 0xFF == sqlite3.SQLITE_BUSY


def _sqlite_code(error: BaseException) -> tuple[object, int | None]:
    cause = error.orig if isinstance(error, DBAPIError) else error
    return cause, getattr(cause, "sqlite_errorcode", None)


def busy_error(path: Path, action: str, seconds: float, error: BaseException) -> SpiderError:
    busy = SpiderError(
        CRAWL_BUSY,
        f"Another connection holds the crawl file {path}, and {action} waited {seconds:g} seconds.",
        hint="Try again when the other process is done with the file.",
        details={"file": str(path)},
    )
    busy.__cause__ = error
    return busy


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
    deadline = time.monotonic() + busy_seconds
    while True:
        connection = sqlite3.connect(uri, uri=True, timeout=busy_seconds)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            # The first read opens the WAL index (-shm), where a killed writer can still hold it.
            connection.execute("PRAGMA schema_version").fetchone()
        except BaseException as error:
            # On any error, as for a file that is not a database: left to the GC, it holds the file.
            connection.close()
            if not isinstance(error, sqlite3.OperationalError) or not _shm_held(error):
                raise
            if time.monotonic() >= deadline:
                raise busy_error(path, "opening", busy_seconds, error) from error
            time.sleep(SHM_RELEASE_CHECK_SECONDS)
        else:
            return connection


def _shm_held(error: sqlite3.Error) -> bool:
    # SQLite 3.50.0 made Windows' winHandleTruncate fail on ERROR_USER_MAPPED_FILE, which -shm gives
    # while a killed process that mapped it is still exiting; winTruncate, used up to 3.49, ignored
    # that error. Like a lock, it ends by itself. Remove once SQLite fixes it.
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_IOERR_TRUNCATE


@contextmanager
def opening(
    path: Path, *, role: ConnectionRole, busy_seconds: float | None = None
) -> Iterator[Engine]:
    read_only = role == "read"
    engine = create_engine(
        "sqlite://",
        creator=lambda: connect(path, read_only=read_only, busy_seconds=busy_seconds),
        poolclass=NullPool,
    )
    if not read_only:
        event.listen(engine, "connect", _own_transactions)
        event.listen(engine, "connect", _synchronous_for_the_journal)
        event.listen(engine, "begin", _begin_immediate)
    # Only the writer's: creating the file and reading it keep SQLite's defaults (design D8).
    if role == "write":
        event.listen(engine, "connect", _writer_settings)
    # Disposed at once, so no handle outlives the operation: Windows could not delete the file.
    try:
        yield engine
    finally:
        engine.dispose()


def _own_transactions(connection: sqlite3.Connection, _: Any) -> None:
    # pysqlite's implicit BEGIN would break SAVEPOINT; the begin event below issues ours.
    connection.isolation_level = None


def _in_wal(connection: sqlite3.Connection) -> bool:
    journal_mode: str = connection.execute("PRAGMA journal_mode").fetchone()[0]
    return journal_mode == "wal"


def _synchronous_for_the_journal(connection: sqlite3.Connection, _: Any) -> None:
    # WAL stays durable at NORMAL; a rollback journal needs FULL for every commit.
    synchronous = "NORMAL" if _in_wal(connection) else "FULL"
    connection.execute(f"PRAGMA synchronous = {synchronous}")


def _writer_settings(connection: sqlite3.Connection, _: Any) -> None:
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute(f"PRAGMA cache_size = -{WRITER_CACHE_KIB}")
    # delete mode is chosen for network shares, where a mapping is only as coherent as the
    # share's client cache. Set to 0, not left alone: the default is a build-time option.
    mmap_size = WRITER_MMAP_BYTES if _in_wal(connection) else 0
    connection.execute(f"PRAGMA mmap_size = {mmap_size}")


def _begin_immediate(connection: Connection) -> None:
    # IMMEDIATE takes the write lock at once, so a busy file fails at BEGIN, not mid-unit.
    connection.exec_driver_sql("BEGIN IMMEDIATE")
