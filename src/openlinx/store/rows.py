"""Pair handler rows with the store function that writes their table."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

# Under TYPE_CHECKING only, so openlinx.store.records, which holds these rows, loads no sqlalchemy.
if TYPE_CHECKING:
    from sqlalchemy import Connection

# One call per handler and URL lets the writer use one executemany for all its rows.
type RowWriter[R] = Callable[[Connection, Sequence[R]], None]


@dataclass(frozen=True, slots=True)
class HandlerRows[R]:
    """One handler's rows for one URL, with the store function of their table."""

    write: RowWriter[R]
    rows: tuple[R, ...]


def write_rows(connection: "Connection", batches: Sequence[HandlerRows[Any]]) -> None:
    for batch in batches:
        batch.write(connection, batch.rows)
