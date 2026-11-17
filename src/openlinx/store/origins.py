"""Record URL origins and their robots.txt and HTTP capability."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Connection, bindparam, select, update
from sqlalchemy.dialects.sqlite import insert

from openlinx.store.records import RobotsTxtRecord
from openlinx.store.schema import origins

type OriginRow = dict[str, Any]

_INSERT_ORIGIN = insert(origins).on_conflict_do_nothing(index_elements=[origins.c.origin])
# Bound as origin in an insert of urls rows: the origins_origin index finds its id.
ORIGIN_ID = select(origins.c.id).where(origins.c.origin == bindparam("origin")).scalar_subquery()
_PLAIN_HTTP = (
    update(origins)
    .where(origins.c.origin == bindparam("origin_key"), origins.c.http_version.is_not("http_1_1"))
    .values(http_version="http_1_1")
)
# Bound names differ from the columns: SQLAlchemy keeps a column's own name for its SET value.
_ROBOTS_TXT = (
    update(origins)
    .where(origins.c.origin == bindparam("origin_key"))
    .values(
        robots_state=bindparam("state"),
        robots_status_code=bindparam("status"),
        robots_fetch_error=bindparam("failure"),
        robots_fetch_error_message=bindparam("failure_message"),
        robots_fetched_at=bindparam("fetched"),
        robots_txt=bindparam("body"),
        robots_crawl_delay_ms=bindparam("delay_ms"),
        robots_sitemaps=bindparam("sitemap_urls"),
    )
)


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


def record_plain_http(origin: str) -> Callable[[Connection], None]:
    """Record capability for a requested plain HTTP origin that the file holds."""
    values = {"origin_key": origin}

    def unit(connection: Connection) -> None:
        connection.execute(_PLAIN_HTTP, values)

    return unit


def record_robots_txt(record: RobotsTxtRecord) -> Callable[[Connection], None]:
    """A unit that records an origin's robots.txt on the row its first URL recorded."""
    values = {
        "origin_key": record.origin,
        "state": record.state,
        "status": record.status_code,
        "failure": record.fetch_error,
        "failure_message": record.fetch_error_message,
        "fetched": record.fetched_at,
        "body": record.text,
        "delay_ms": record.crawl_delay_ms,
        "sitemap_urls": record.sitemaps,
    }

    def unit(connection: Connection) -> None:
        connection.execute(_ROBOTS_TXT, values)

    return unit
