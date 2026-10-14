"""Store rows that handlers return, each written by its table's store module (020 D14)."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import Connection

type RowWriter = Callable[[Connection, Any], None]


def write_rows(
    connection: Connection, rows: Sequence[object], writers: Mapping[type, RowWriter]
) -> None:
    for row in rows:
        writer = writers.get(type(row))
        if writer is None:
            raise TypeError(f"no row writer is registered for {type(row).__name__}")
        writer(connection, row)
