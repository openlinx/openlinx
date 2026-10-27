"""The urls table's units: the frontier and each URL's outcome (020-add-crawl-core D1, D2, D14)."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import (
    Connection,
    Insert,
    bindparam,
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
    DiscoveredVia,
    DiscoverySkipReason,
    ErroredUrl,
    FetchedUrl,
    NewUrl,
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
_INSERT_URL = _INSERT.on_conflict_do_nothing(index_elements=[urls.c.url])
# A followed Link re-queues a URL that only unfollowed Links reached, as found through it, and
# gives the shorter path that a Checked URL found after its depth closed (design D3) to a URL
# still queued, or skipped beyond the depth limit, which dispatch then decides again; every
# other conflict changes nothing, so a replayed unit gives the same rows (design D5).
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
        )
    )
    & (_INSERT.excluded.fetch_state == literal_column("'queued'")),
)
_URL_ID = select(urls.c.id).where(urls.c.url == bindparam("url"))
_FOUND_ON = select(urls.c.discovered_via, urls.c.found_on_url_id).where(
    urls.c.id == bindparam("url_id")
)
_REDIRECT_URL_ID = (
    update(urls)
    .where(urls.c.id == bindparam("url_id"))
    .values(
        redirect_url_id=select(urls.c.id).where(urls.c.url == bindparam("target")).scalar_subquery()
    )
)
_DEPTH = select(urls.c.crawl_depth).where(urls.c.id == bindparam("url_id"))
# Bound names differ from the columns: SQLAlchemy keeps a column's own name for its SET value.
_URL_ROW = update(urls).where(urls.c.id == bindparam("url_id"))
_RECLASSIFIED = _URL_ROW.values(is_internal=bindparam("internal"), in_scope=bindparam("scoped"))
_FETCHED = _URL_ROW.values(
    fetch_state="fetched",
    status_code=bindparam("response_status"),
    content_type=bindparam("response_type"),
    response_time_ms=bindparam("response_ms"),
    fetched_at=bindparam("request_at"),
    attempt_count=bindparam("attempts"),
    redirect_location=bindparam("location"),
    parsed=bindparam("is_parsed"),
    parse_error=bindparam("parse_failure"),
    parse_error_message=bindparam("parse_failure_message"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
)
_SKIPPED = _URL_ROW.where(urls.c.crawl_depth == bindparam("decided_depth")).values(
    fetch_state="skipped",
    skip_reason=bindparam("reason"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
)
_ERRORED = _URL_ROW.values(
    fetch_state="error",
    fetch_error=bindparam("failure"),
    fetch_error_message=bindparam("failure_message"),
    fetched_at=bindparam("request_at"),
    attempt_count=bindparam("attempts"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
)
_UNWRITTEN = _URL_ROW.values(
    fetch_state="error",
    fetch_error="record_failed",
    fetch_error_message=bindparam("failure_message"),
    attempt_count=bindparam("attempts"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
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

    def unit(connection: Connection) -> int:
        insert_urls(connection, _INSERT_URL, [row])
        url_id: int = connection.execute(_URL_ID, {"url": url}).scalar_one()
        return url_id

    return unit


def insert_urls(
    connection: Connection, statement: Insert, rows: Sequence[Mapping[str, Any]]
) -> None:
    """The one way rows go into urls: each binds its origin, whose row is recorded first, or
    the insert fails on a NULL origin_id (design D18)."""
    record_origins(connection, origin_rows(rows))
    connection.execute(statement, list(rows))


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
                chain_via=_chain_via(connection, row.discovered_via, row.found_on_url_id),
            )
            for row in rows
        )

    return unit


def _chain_via(connection: Connection, via: DiscoveredVia, found_on: int | None) -> DiscoveredVia:
    # Point reads back along the chain, for redirect targets only, at most 20 hops: a loop
    # ends there (022-add-fetch-policy D2).
    for _ in range(20):
        if via != "redirect" or found_on is None:
            break
        via, found_on = connection.execute(_FOUND_ON, {"url_id": found_on}).one()
    return via


def _hops_to(connection: Connection, url_id: int, limit: int) -> int:
    # The consecutive redirects that led to the URL, read back from the file, so a replayed
    # or continued unit counts the same; at most `limit` point reads (022-add-fetch-policy D2).
    hops = 0
    while hops < limit:
        via, found_on = connection.execute(_FOUND_ON, {"url_id": url_id}).one()
        if via != "redirect" or found_on is None:
            break
        hops, url_id = hops + 1, found_on
    return hops


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
        "attempts": fetched.attempt_count,
        "location": fetched.redirect_location,
        "request_at": fetched.fetched_at,
        "is_parsed": fetched.parsed,
        "parse_failure": fetched.parse_error,
        "parse_failure_message": fetched.parse_error_message,
        "robots_blocked": fetched.blocked_by_robots_txt,
    }
    new_rows = [_new_row(new, url_id) for new in fetched.discovered]

    redirect = fetched.redirect
    redirect_row = None if redirect is None else _new_row(redirect, url_id)
    max_redirects = fetched.max_redirects

    def unit(connection: Connection) -> None:
        connection.execute(_FETCHED, values)
        if not new_rows and redirect_row is None:
            write_rows(connection, fetched.rows)
            return
        # The stored depth, which a Checked URL answering late may have lowered while the URL
        # was in flight, so what it links to stays one deeper than it (design D3).
        depth: int = connection.execute(_DEPTH, {"url_id": url_id}).scalar_one()
        # The unique index urls_url is the only dedup: no URL map in memory (design D1).
        if new_rows:
            rows = [{**row, "crawl_depth": depth + 1} for row in new_rows]
            insert_urls(connection, _INSERT_DISCOVERED, rows)
        if redirect_row is not None:
            # A redirect is no Link: its target keeps the depth (022 design D2).
            target = {**redirect_row, "crawl_depth": depth}
            if _hops_to(connection, url_id, max_redirects) >= max_redirects:
                target |= {"fetch_state": "skipped", "skip_reason": "max_redirects"}
            insert_urls(connection, _INSERT_DISCOVERED, [target])
            connection.execute(_REDIRECT_URL_ID, {"url_id": url_id, "target": redirect_row["url"]})
        write_rows(connection, fetched.rows)

    return unit


def _new_row(new: NewUrl, found_on: int) -> dict[str, Any]:
    return {
        "url": new.url,
        "host": url_host(new.url),
        "origin": url_origin(new.url),
        "is_internal": new.is_internal,
        "in_scope": new.in_scope,
        "discovered_via": new.discovered_via,
        "found_on_url_id": found_on,
        "fetch_state": "queued" if new.skip_reason is None else "skipped",
        "skip_reason": new.skip_reason,
        "parsed": False,
    }


def reclassify_urls(decisions: Sequence[tuple[int, bool, bool]]) -> UrlUnit:
    """A unit that writes is_internal and in_scope again, by URL id: the URLs of a Seed's
    Redirect Chain, against the Scope it ended in (022-add-fetch-policy D3)."""
    rows = [
        {"url_id": url_id, "internal": internal, "scoped": scoped}
        for url_id, internal, scoped in decisions
    ]

    def unit(connection: Connection) -> None:
        connection.execute(_RECLASSIFIED, rows)

    return unit


def record_skipped(skipped: SkippedUrl) -> UrlUnit:
    """A unit that records a URL as not requested, why, and its rows, unless a shorter path
    lowered its depth after the skip was decided: it then stays queued (design D5)."""
    values = {
        "url_id": skipped.url_id,
        "reason": skipped.skip_reason,
        "decided_depth": skipped.crawl_depth,
        "robots_blocked": skipped.blocked_by_robots_txt,
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
        "attempts": errored.attempt_count,
        "robots_blocked": errored.blocked_by_robots_txt,
    }

    def unit(connection: Connection) -> None:
        connection.execute(_ERRORED, values)
        write_rows(connection, errored.rows)

    return unit


def record_unwritten(
    url_id: int, message: str, *, blocked_by_robots_txt: bool | None, attempt_count: int
) -> UrlUnit:
    """The fallback unit of a URL whose own unit failed: only its state, what robots.txt said
    of it, and the requests made for it (design D2)."""
    values = {
        "url_id": url_id,
        "failure_message": message,
        "robots_blocked": blocked_by_robots_txt,
        "attempts": attempt_count,
    }

    def unit(connection: Connection) -> None:
        connection.execute(_UNWRITTEN, values)

    return unit


def url_counts() -> Callable[[Connection], UrlCounts]:
    """A unit that only reads: the counts of a Crawl's result, from the rows (design D10)."""

    def unit(connection: Connection) -> UrlCounts:
        return UrlCounts(**connection.execute(_COUNTS).one()._mapping)

    return unit
