"""Own one database engine per crawl-file operation."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path, PurePath
from typing import Any, Literal
from urllib.parse import quote

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from openlinx.output.codes import CRAWL_BUSY
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.identity import verify_file_identity
from openlinx.store.records import CrawlFileIdentity

READER_BUSY_SECONDS = 5.0
WRITER_BUSY_SECONDS = 30.0
# How often opening looks again at a -shm file that a killed writer still holds.
SHM_RELEASE_CHECK_SECONDS = 0.05

WRITER_CACHE_KIB = 65_536
WRITER_MMAP_BYTES = 268_435_456

type ConnectionRole = Literal["create", "read", "write", "control"]

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


def is_read_only(error: BaseException) -> bool:
    """Include extended SQLite READONLY codes without classifying other I/O errors."""
    _, code = _sqlite_code(error)
    return code is not None and code & 0xFF == sqlite3.SQLITE_READONLY


def _sqlite_code(error: BaseException) -> tuple[object, int | None]:
    cause = error.orig if isinstance(error, DBAPIError) else error
    return cause, getattr(cause, "sqlite_errorcode", None)


def busy_error(path: Path, action: str, seconds: float, error: BaseException) -> OpenLinxError:
    busy = OpenLinxError(
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
    path: Path,
    *,
    read_only: bool = False,
    busy_seconds: float | None = None,
    identity: CrawlFileIdentity | None = None,
    single_link: bool = False,
) -> sqlite3.Connection:
    # rw, not SQLite's default rwc: a missing crawl file is an error, never a new empty file.
    resolved = path.resolve() if identity is None else identity.path
    uri = file_uri(resolved) + ("?mode=ro" if read_only else "?mode=rw")
    # A reader gives up after 5 s (crawl_busy); the writer waits out a reader's longest wait.
    if busy_seconds is None:
        busy_seconds = READER_BUSY_SECONDS if read_only else WRITER_BUSY_SECONDS
    deadline = time.monotonic() + busy_seconds
    verify_identity = identity is not None or single_link
    while True:
        if verify_identity:
            verify_file_identity(path, identity, at=resolved, single_link=single_link)
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=busy_seconds)
        except sqlite3.Error as error:
            # A missing or changed file can fail the open before the post-open check.
            if verify_identity:
                try:
                    verify_file_identity(path, identity, at=resolved, single_link=single_link)
                except OpenLinxError as changed:
                    raise changed from error
            raise
        try:
            if verify_identity:
                verify_file_identity(path, identity, at=resolved, single_link=single_link)
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
    path: Path,
    *,
    role: ConnectionRole,
    busy_seconds: float | None = None,
    disk_temp_store: bool = False,
    identity: CrawlFileIdentity | None = None,
) -> Iterator[Engine]:
    read_only = role == "read"
    engine = create_engine(
        "sqlite://",
        creator=lambda: connect(
            path,
            read_only=read_only,
            busy_seconds=busy_seconds,
            identity=identity,
            # The control role writes without the claim that normally checks hard links.
            single_link=role == "control",
        ),
        poolclass=NullPool,
    )
    if not read_only:
        event.listen(engine, "connect", _own_transactions)
        event.listen(engine, "connect", _synchronous_for_the_journal)
        event.listen(engine, "begin", _begin_immediate)
    # Only the writer's: creating the file and reading it keep SQLite's defaults
    # (017-speed-up-crawl-writer D8).
    if role == "write":
        event.listen(engine, "connect", partial(_writer_settings, disk_temp_store=disk_temp_store))
    if role == "control":
        event.listen(engine, "connect", _control_writes_only)
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
    # WAL/NORMAL survives a process crash, but a power loss can undo recent commits.
    # Rollback journals use FULL to sync at commit.
    synchronous = "NORMAL" if _in_wal(connection) else "FULL"
    connection.execute(f"PRAGMA synchronous = {synchronous}")


def _writer_settings(connection: sqlite3.Connection, _: Any, *, disk_temp_store: bool) -> None:
    temp_store = "FILE" if disk_temp_store else "MEMORY"
    connection.execute(f"PRAGMA temp_store = {temp_store}")
    connection.execute(f"PRAGMA cache_size = -{WRITER_CACHE_KIB}")
    # Rollback-journal mode is chosen for network shares, where a mapping is only as coherent as the
    # share's client cache. Set to 0, not left alone: the default is a build-time option.
    mmap_size = WRITER_MMAP_BYTES if _in_wal(connection) else 0
    connection.execute(f"PRAGMA mmap_size = {mmap_size}")


def _begin_immediate(connection: Connection) -> None:
    # IMMEDIATE takes the write lock at once, so a busy file fails at BEGIN, not mid-unit.
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def _control_writes_only(connection: sqlite3.Connection, _: Any) -> None:
    from openlinx.store.schema import public_tables

    allowed = {table.name for table in public_tables() if table.info.get("control")}

    def authorize(
        action: int,
        table: str | None,
        _column: str | None,
        database: str | None,
        _source: str | None,
    ) -> int:
        if action in (sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_TRANSACTION):
            return sqlite3.SQLITE_OK
        if (
            action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
            and database == "main"
            and table in allowed
        ):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    connection.set_authorizer(authorize)
