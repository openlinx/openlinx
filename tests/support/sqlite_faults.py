"""A -shm file still held by a killed writer, as SQLite reports it (015-add-crawl-store)."""

import sqlite3
from typing import Any

import pytest

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
