"""A declared table with a reference and secondary indexes (018-add-schema-conventions D4)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Column, ForeignKey, Index, Integer, Text

from spider.store.schema import metadata, public_table


@contextmanager
def indexed_rows_declared() -> Iterator[None]:
    """`indexed_rows`, declared the way 020's urls will be, until the block ends.

    Safe because the tests run serially; under xdist this must use an isolated MetaData copy.
    """
    table = public_table(
        "indexed_rows",
        Column("id", Integer, primary_key=True, comment="The row id."),
        Column("url", Text, nullable=False, comment="A URL."),
        Column("state", Text, nullable=False, comment="A state."),
        Column(
            "found_on_row_id",
            Integer,
            ForeignKey("indexed_rows.id"),
            comment="The row it was found on.",
        ),
        comment="Rows with a reference and secondary indexes.",
        change=99,
    )
    Index(
        "indexed_rows_url",
        table.c.url,
        unique=True,
        info={"description": "Finds a row by its URL."},
    )
    Index(
        "indexed_rows_state_id",
        table.c.state,
        table.c.id,
        sqlite_where=table.c.state == "queued",
        info={"description": "Lists queued rows in id order."},
    )
    try:
        yield
    finally:
        metadata.remove(table)
