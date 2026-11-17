"""Record URL origins and their robots.txt and HTTP capability."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import (
    Column,
    Connection,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    bindparam,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.schema import CreateTable

from openlinx.store.records import HttpVersion, RobotsTxtRecord
from openlinx.store.schema import origins

type OriginRow = dict[str, Any]

_INSERT_ORIGIN = insert(origins).on_conflict_do_nothing(index_elements=[origins.c.origin])
# Bound as origin in an insert of urls rows: the origins_origin index finds its id.
ORIGIN_ID = select(origins.c.id).where(origins.c.origin == bindparam("origin")).scalar_subquery()
_HTTP_VERSION = (
    update(origins)
    .where(
        origins.c.origin == bindparam("origin_key"),
        origins.c.http_version.is_distinct_from(bindparam("capability")),
    )
    .values(http_version=bindparam("capability"))
)
# The writer connection lasts one run. A cursor over claim IDs keeps completed and pending
# origins deduplicated without retaining either in memory or changing the Crawl schema.
_claims = Table(
    "http_version_claims",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("origin", Text, nullable=False, unique=True),
    Column("deadline", Float, nullable=False),
    schema="temp",
    prefixes=["TEMPORARY"],
)
_CREATE_CLAIMS = CreateTable(_claims, if_not_exists=True)
_CLAIM = insert(_claims).on_conflict_do_nothing(index_elements=[_claims.c.origin])
_NEXT_CLAIM = (
    select(_claims).where(_claims.c.id > bindparam("after")).order_by(_claims.c.id).limit(1)
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


def init_http_version_claims(connection: Connection) -> None:
    connection.execute(_CREATE_CLAIMS)


def claim_http_version(origin: str, deadline: float) -> Callable[[Connection], bool]:
    """Queue only the first request of an origin, clearing any earlier run's measurement."""

    def unit(connection: Connection) -> bool:
        claimed = connection.execute(_CLAIM, {"origin": origin, "deadline": deadline})
        if claimed.rowcount != 1:
            return False
        connection.execute(_HTTP_VERSION, {"origin_key": origin, "capability": None})
        return True

    return unit


def next_http_version_claim(after: int) -> Callable[[Connection], tuple[int, str, float] | None]:
    def unit(connection: Connection) -> tuple[int, str, float] | None:
        row = connection.execute(_NEXT_CLAIM, {"after": after}).one_or_none()
        return None if row is None else (int(row.id), str(row.origin), float(row.deadline))

    return unit


def record_http_version(origin: str, version: HttpVersion) -> Callable[[Connection], None]:
    values = {"origin_key": origin, "capability": version}

    def unit(connection: Connection) -> None:
        connection.execute(_HTTP_VERSION, values)

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
