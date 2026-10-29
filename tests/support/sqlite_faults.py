"""SQLite failures that tests cannot cause for real: a -shm file still held by a killed writer
(015-add-crawl-store), and a full disk (020-add-crawl-core)."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import Engine, event

SQLITE_IOERR_TRUNCATE = 1546


class _Held:
    """A connection whose first statement fails the way SQLite fails on a held -shm file."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, *args: Any) -> sqlite3.Cursor:
        error = sqlite3.OperationalError("disk I/O error")
        error.sqlite_errorcode = SQLITE_IOERR_TRUNCATE
        error.sqlite_errorname = "SQLITE_IOERR_TRUNCATE"
        raise error

    def close(self) -> None:
        self._connection.close()


def shm_held(monkeypatch: pytest.MonkeyPatch, opens: int | None) -> None:
    """The next `opens` SQLite connections fail as if -shm were held; None means every one."""
    real = sqlite3.connect
    left = opens

    def connect(*args: Any, **kwargs: Any) -> Any:
        nonlocal left
        connection = real(*args, **kwargs)
        if left is not None and left <= 0:
            return connection
        if left is not None:
            left -= 1
        return _Held(connection)

    monkeypatch.setattr(sqlite3, "connect", connect)


@contextmanager
def disk_full_after(pages: int) -> Iterator[None]:
    """SQLite reports a full disk once a crawl file grows `pages` pages past its size when the
    connection opened, as on a disk with that much room left. A file being created is not
    capped, and the next connection gets room again, as one opened after space was freed."""

    def cap(connection: sqlite3.Connection, _: Any) -> None:
        if connection.execute("SELECT 1 FROM sqlite_schema WHERE name = 'crawl'").fetchone():
            (count,) = connection.execute("PRAGMA page_count").fetchone()
            connection.execute(f"PRAGMA max_page_count = {count + pages}")

    event.listen(Engine, "connect", cap)
    try:
        yield
    finally:
        event.remove(Engine, "connect", cap)
