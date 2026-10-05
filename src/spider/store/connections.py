"""Opening crawl files through URIs, one engine per operation (design D2 of 015-add-crawl-store)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from urllib.parse import quote

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

from spider.store.records import JournalMode


def file_uri(path: PurePath) -> str:
    posix = quote(path.as_posix(), safe="/:")
    # A UNC path keeps its host in the path (file:////host/share): SQLite refuses any URI
    # authority but localhost, which is why Path.as_uri() cannot be used.
    return f"file://{posix}" if posix.startswith("/") else f"file:///{posix}"


def connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    uri = file_uri(path.resolve()) + ("?mode=ro" if read_only else "")
    return sqlite3.connect(uri, uri=True)


@contextmanager
def opening(
    path: Path, *, read_only: bool = False, journal_mode: JournalMode | None = None
) -> Iterator[Engine]:
    def creator() -> sqlite3.Connection:
        connection = connect(path, read_only=read_only)
        if journal_mode is not None:
            # WAL stays durable at NORMAL; a rollback journal needs FULL for every commit.
            synchronous = "NORMAL" if journal_mode == "wal" else "FULL"
            connection.execute(f"PRAGMA synchronous = {synchronous}")
        return connection

    engine = create_engine("sqlite://", creator=creator, poolclass=NullPool)
    # Disposed at once, so no handle outlives the operation: Windows could not delete the file.
    try:
        yield engine
    finally:
        engine.dispose()
