"""The units of the origins table: each URL's origin, with the URL's own unit (020 D14, D18)."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Connection, bindparam, select
from sqlalchemy.dialects.sqlite import insert

from spider.store.schema import origins

type OriginRow = dict[str, Any]

_INSERT_ORIGIN = insert(origins).on_conflict_do_nothing(index_elements=[origins.c.origin])
# Bound as origin in an insert of urls rows: the origins_origin index finds its id.
ORIGIN_ID = select(origins.c.id).where(origins.c.origin == bindparam("origin")).scalar_subquery()


def origin_rows(url_rows: Iterable[Mapping[str, Any]]) -> tuple[OriginRow, ...]:
    """The origins rows of urls rows, which bind their origin, each origin once."""
    rows: dict[str, OriginRow] = {}
    for url_row in url_rows:
        origin = url_row["origin"]
        if origin not in rows:
            rows[origin] = {
                "origin": origin,
                "host": url_row["host"],
                "is_internal": url_row["is_internal"],
            }
    return tuple(rows.values())


def record_origins(connection: Connection, rows: Sequence[OriginRow]) -> None:
    """Records each origin the file does not hold yet, in the unit of its first URL."""
    if rows:
        connection.execute(_INSERT_ORIGIN, list(rows))
