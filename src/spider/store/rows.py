"""Handler rows, each written by its table's store module (020-add-crawl-core D9, D14)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

# Under TYPE_CHECKING only, so spider.store.records, which holds these rows, loads no sqlalchemy.
if TYPE_CHECKING:
    from sqlalchemy import Connection

type RowWriter[R] = Callable[[Connection, R], None]


@dataclass(frozen=True, slots=True)
class HandlerRows[R]:
    """One handler's rows for one URL, with the store function of their table."""

    write: RowWriter[R]
    rows: tuple[R, ...]


def write_rows(connection: "Connection", batches: Sequence[HandlerRows[Any]]) -> None:
    for batch in batches:
        for row in batch.rows:
            batch.write(connection, row)
