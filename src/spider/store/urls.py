"""The urls table's units: the frontier and each URL's outcome (020-add-crawl-core D1, D2, D14)."""

from collections.abc import Callable

from sqlalchemy import (
    ColumnElement,
    Connection,
    bindparam,
    case,
    func,
    literal_column,
    null,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert

from spider.crawl.urls import NormalizedUrl, url_host, url_origin
from spider.store.origins import ORIGIN_ID, origin_rows, record_origins
from spider.store.records import (
    RESOURCE_LINK_TYPES,
    DiscoverySkipReason,
    Dispatched,
    ErroredUrl,
    FetchedUrl,
    QueuedUrl,
    SkippedUrl,
    UrlCounts,
)
from spider.store.rows import write_rows
from spider.store.schema import literal_values, urls

type UrlUnit = Callable[[Connection], None]

# Built once: units run once per URL (017-speed-up-crawl-writer D9).
# Each row binds its origin, whose row the unit records first (design D18).
_INSERT = insert(urls).values(origin_id=ORIGIN_ID)


def _is_resource(discovered_via: ColumnElement[str]) -> ColumnElement[bool]:
    # An OR chain, never IN (ADR-0005).
    return or_(
        *(discovered_via == literal_column(f"'{kind}'") for kind in sorted(RESOURCE_LINK_TYPES))
    )


_INSERT_URL = _INSERT.on_conflict_do_nothing(index_elements=[urls.c.url])
# A followed Link re-queues a URL that only unfollowed Links reached, as found through it, and
# gives the shorter path that a Checked URL found after its depth closed (design D3) to a URL
# still queued, or skipped beyond the depth limit, which dispatch then decides again. A
# Resource Link raises a still-queued URL that a followed Link recorded first, at its depth
# or a shorter one, so the Resource is requested. Every other conflict changes nothing, so
# a replayed unit gives the same rows (design D5).
_INSERT_DISCOVERED = _INSERT.on_conflict_do_update(
    index_elements=[urls.c.url],
    set_={
        "fetch_state": _INSERT.excluded.fetch_state,
        "skip_reason": null(),
        "crawl_depth": _INSERT.excluded.crawl_depth,
        "discovered_via": _INSERT.excluded.discovered_via,
        "found_on_url_id": _INSERT.excluded.found_on_url_id,
    },
    where=(
        or_(
            *(
                urls.c.skip_reason == literal_column(f"'{reason}'")
                for reason in literal_values(DiscoverySkipReason)
            ),
            (
                (urls.c.fetch_state == literal_column("'queued'"))
                | (urls.c.skip_reason == literal_column("'max_depth'"))
            )
            & (urls.c.crawl_depth > _INSERT.excluded.crawl_depth),
            (urls.c.fetch_state == literal_column("'queued'"))
            & _is_resource(_INSERT.excluded.discovered_via)
            & ~_is_resource(urls.c.discovered_via)
            & (urls.c.crawl_depth >= _INSERT.excluded.crawl_depth),
        )
    )
    & (_INSERT.excluded.fetch_state == literal_column("'queued'")),
)
_URL_ID = select(urls.c.id).where(urls.c.url == bindparam("url"))
_DEPTH = select(urls.c.crawl_depth).where(urls.c.id == bindparam("url_id"))
# Bound names differ from the columns: SQLAlchemy keeps a column's own name for its SET value.
_URL_ROW = update(urls).where(urls.c.id == bindparam("url_id"))
_AT_THE_DISPATCHED_DEPTH = urls.c.crawl_depth == bindparam("dispatched_depth")
# What the dispatch acted on, unless a late check lowered the URL meanwhile (design D5).
_DISPATCHED = {
    "discovered_via": case(
        (_AT_THE_DISPATCHED_DEPTH, bindparam("dispatched_via")), else_=urls.c.discovered_via
    ),
    "found_on_url_id": case(
        (_AT_THE_DISPATCHED_DEPTH, bindparam("dispatched_found_on")),
        else_=urls.c.found_on_url_id,
    ),
}
_FETCHED = _URL_ROW.values(
    fetch_state="fetched",
    status_code=bindparam("response_status"),
    content_type=bindparam("response_type"),
    response_time_ms=bindparam("response_ms"),
    fetched_at=bindparam("request_at"),
    parsed=bindparam("is_parsed"),
    parse_error=bindparam("parse_failure"),
    parse_error_message=bindparam("parse_failure_message"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_DISPATCHED,
)
_SKIPPED = _URL_ROW.where(_AT_THE_DISPATCHED_DEPTH).values(
    fetch_state="skipped",
    skip_reason=bindparam("reason"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_DISPATCHED,
)
_ERRORED = _URL_ROW.values(
    fetch_state="error",
    fetch_error=bindparam("failure"),
    fetch_error_message=bindparam("failure_message"),
    fetched_at=bindparam("request_at"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_DISPATCHED,
)
_UNWRITTEN = _URL_ROW.values(
    fetch_state="error",
    fetch_error="record_failed",
    fetch_error_message=bindparam("failure_message"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_DISPATCHED,
)
# A literal, as the partial index urls_crawl_depth_id is declared, so the frontier reads use it
# without the plan depending on a bound value (design D1).
_IS_QUEUED = urls.c.fetch_state == literal_column("'queued'")
_QUEUED = (
    select(urls.c.id, urls.c.url, urls.c.crawl_depth, urls.c.discovered_via, urls.c.found_on_url_id)
    .where(
        _IS_QUEUED,
        urls.c.crawl_depth == bindparam("depth"),
        urls.c.id > bindparam("after"),
    )
    .order_by(urls.c.id)
    .limit(bindparam("size"))
)
_COUNTS = select(
    func.count().label("discovered"),
    func.count().filter(urls.c.fetch_state == "fetched").label("fetched"),
    func.count().filter(urls.c.fetch_state == "error").label("errors"),
    func.count().filter(urls.c.fetch_state == "skipped").label("skipped"),
    func.count().filter(_IS_QUEUED).label("queued"),
    func.count().filter(urls.c.parsed == 1).label("pages"),
    *(
        func.count()
        .filter(urls.c.status_code.between(low, low + 99))
        .label(f"status_{low // 100}xx")
        for low in (200, 300, 400, 500)
    ),
    func.count().filter(~urls.c.status_code.between(200, 599)).label("status_other"),
)
_NEXT_DEPTH = select(func.min(urls.c.crawl_depth)).where(
    _IS_QUEUED, urls.c.crawl_depth > bindparam("depth")
)


def record_seed(
    url: NormalizedUrl, *, is_internal: bool, in_scope: bool
) -> Callable[[Connection], int]:
    """A unit that records the Seed as queued, once, and returns its id."""
    row = {
        "url": url,
        "host": url_host(url),
        "origin": url_origin(url),
        "is_internal": is_internal,
        "in_scope": in_scope,
        "crawl_depth": 0,
        "discovered_via": "seed",
        "fetch_state": "queued",
        "parsed": False,
    }
    origins = origin_rows([row])

    def unit(connection: Connection) -> int:
        record_origins(connection, origins)
        connection.execute(_INSERT_URL, row)
        url_id: int = connection.execute(_URL_ID, {"url": url}).scalar_one()
        return url_id

    return unit


def queued_batch(
    depth: int, after: int, size: int
) -> Callable[[Connection], tuple[QueuedUrl, ...]]:
    """A unit that only reads: the next queued URLs at `depth` whose id is above `after`."""

    def unit(connection: Connection) -> tuple[QueuedUrl, ...]:
        rows = connection.execute(_QUEUED, {"depth": depth, "after": after, "size": size})
        # The one place the frontier reads urls.url back (design D13).
        return tuple(
            QueuedUrl(
                id=row.id,
                url=NormalizedUrl(row.url),
                crawl_depth=row.crawl_depth,
                discovered_via=row.discovered_via,
                found_on_url_id=row.found_on_url_id,
            )
            for row in rows
        )

    return unit


def next_depth(depth: int) -> Callable[[Connection], int | None]:
    """A unit that only reads: the shallowest depth deeper than `depth` with a queued URL."""

    def unit(connection: Connection) -> int | None:
        deeper: int | None = connection.execute(_NEXT_DEPTH, {"depth": depth}).scalar()
        return deeper

    return unit


def record_fetched(fetched: FetchedUrl) -> UrlUnit:
    """A unit that records the URL's response, the URLs discovered from it and its rows."""
    url_id = fetched.url_id
    values = {
        "url_id": url_id,
        "response_status": fetched.status_code,
        "response_type": fetched.content_type,
        "response_ms": fetched.response_time_ms,
        "request_at": fetched.fetched_at,
        "is_parsed": fetched.parsed,
        "parse_failure": fetched.parse_error,
        "parse_failure_message": fetched.parse_error_message,
        "robots_blocked": fetched.blocked_by_robots_txt,
        **_dispatched(fetched.dispatched),
    }
    new_rows = [
        {
            "url": new.url,
            "host": url_host(new.url),
            "origin": url_origin(new.url),
            "is_internal": new.is_internal,
            "in_scope": new.in_scope,
            "discovered_via": new.discovered_via,
            "found_on_url_id": url_id,
            "fetch_state": "queued" if new.skip_reason is None else "skipped",
            "skip_reason": new.skip_reason,
            "parsed": False,
        }
        for new in fetched.discovered
    ]
    origins = origin_rows(new_rows)

    def unit(connection: Connection) -> None:
        connection.execute(_FETCHED, values)
        record_origins(connection, origins)
        # The unique index urls_url is the only dedup: no URL map in memory (design D1).
        if new_rows:
            # The stored depth, which a Checked URL answering late may have lowered while the
            # URL was in flight, so what it links to stays one deeper than it (design D3).
            depth = connection.execute(_DEPTH, {"url_id": url_id}).scalar_one() + 1
            rows = [{**row, "crawl_depth": depth} for row in new_rows]
            connection.execute(_INSERT_DISCOVERED, rows)
        write_rows(connection, fetched.rows)

    return unit


def record_skipped(skipped: SkippedUrl) -> UrlUnit:
    """A unit that records a URL as not requested, why, and its rows, unless a shorter path
    lowered its depth after the skip was decided: it then stays queued (design D5)."""
    values = {
        "url_id": skipped.url_id,
        "reason": skipped.skip_reason,
        "robots_blocked": skipped.blocked_by_robots_txt,
        **_dispatched(skipped.dispatched),
    }

    def unit(connection: Connection) -> None:
        if connection.execute(_SKIPPED, values).rowcount:
            write_rows(connection, skipped.rows)

    return unit


def record_error(errored: ErroredUrl) -> UrlUnit:
    """A unit that records a URL whose request got no HTTP response, why, and its rows."""
    values = {
        "url_id": errored.url_id,
        "failure": errored.fetch_error,
        "failure_message": errored.fetch_error_message,
        "request_at": errored.fetched_at,
        "robots_blocked": errored.blocked_by_robots_txt,
        **_dispatched(errored.dispatched),
    }

    def unit(connection: Connection) -> None:
        connection.execute(_ERRORED, values)
        write_rows(connection, errored.rows)

    return unit


def record_unwritten(
    url_id: int, message: str, *, blocked_by_robots_txt: bool | None, dispatched: Dispatched
) -> UrlUnit:
    """The fallback unit of a URL whose own unit failed: only its state, and what robots.txt
    said of it (design D2)."""
    values = {
        "url_id": url_id,
        "failure_message": message,
        "robots_blocked": blocked_by_robots_txt,
        **_dispatched(dispatched),
    }

    def unit(connection: Connection) -> None:
        connection.execute(_UNWRITTEN, values)

    return unit


def _dispatched(dispatched: Dispatched) -> dict[str, object]:
    return {
        "dispatched_depth": dispatched.crawl_depth,
        "dispatched_via": dispatched.discovered_via,
        "dispatched_found_on": dispatched.found_on_url_id,
    }


def url_counts() -> Callable[[Connection], UrlCounts]:
    """A unit that only reads: the counts of a Crawl's result, from the rows (design D10)."""

    def unit(connection: Connection) -> UrlCounts:
        return UrlCounts(**connection.execute(_COUNTS).one()._mapping)

    return unit
