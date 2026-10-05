"""Opening crawl files through URIs, one engine per operation (design D2 of 015-add-crawl-store)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import quote

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.pool import NullPool


def file_uri(path: PurePath) -> str:
    posix = quote(path.as_posix(), safe="/:")
    # A UNC path keeps its host in the path (file:////host/share): SQLite refuses any URI
    # authority but localhost, which is why Path.as_uri() cannot be used.
    return f"file://{posix}" if posix.startswith("/") else f"file:///{posix}"


def connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    uri = file_uri(path.resolve()) + ("?mode=ro" if read_only else "")
    return sqlite3.connect(uri, uri=True)


@contextmanager
def opening(path: Path, *, read_only: bool = False) -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", creator=lambda: connect(path, read_only=read_only), poolclass=NullPool
    )
    if not read_only:
        event.listen(engine, "connect", _own_transactions)
        event.listen(engine, "begin", _begin_immediate)
    # Disposed at once, so no handle outlives the operation: Windows could not delete the file.
    try:
        yield engine
    finally:
        engine.dispose()


def _own_transactions(connection: sqlite3.Connection, _: Any) -> None:
    # pysqlite's implicit BEGIN would break SAVEPOINT; the begin event below issues ours.
    connection.isolation_level = None
    (journal_mode,) = connection.execute("PRAGMA journal_mode").fetchone()
    # WAL stays durable at NORMAL; a rollback journal needs FULL for every commit.
    synchronous = "NORMAL" if journal_mode == "wal" else "FULL"
    connection.execute(f"PRAGMA synchronous = {synchronous}")


def _begin_immediate(connection: Connection) -> None:
    # IMMEDIATE takes the write lock at once, so a busy file fails at BEGIN, not mid-unit.
    connection.exec_driver_sql("BEGIN IMMEDIATE")
