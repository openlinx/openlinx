"""The urls table's units: the frontier and each URL's outcome (020-add-crawl-core D1, D2, D14)."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Connection,
    Insert,
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
    ErroredUrl,
    FetchedUrl,
    NewUrl,
    Provenance,
    QueuedUrl,
    Reclassified,
    SkippedUrl,
    UrlCounts,
)
from spider.store.redirects import chain_via, link_redirect, past_the_hop_limit
from spider.store.rows import write_rows
from spider.store.schema import literal_values, urls

# True once it recorded the URL's outcome; a skip that a lowering or a raise overtook
# records nothing, and the URL is decided again (design D5).
type UrlUnit = Callable[[Connection], bool]


def _literal_one_of(column: ColumnElement[str], values: Iterable[str]) -> ColumnElement[bool]:
    # An OR chain, never IN (ADR-0005), of statement-level literals, as an executemany needs.
    return or_(*(column == literal_column(f"'{value}'") for value in sorted(values)))


# A URL of a Seed's Redirect Chain: its id and URL, in the chain's order.
type SeedChainUrls = tuple[tuple[int, NormalizedUrl], ...]

# Built once: units run once per URL (017-speed-up-crawl-writer D9).
# Each row binds its origin, whose row the unit records first (design D18).
_INSERT = insert(urls).values(origin_id=ORIGIN_ID)


_INSERT_URL = _INSERT.on_conflict_do_nothing(index_elements=[urls.c.url])
# A row that dispatch decides again when a better Link reaches it.
_DECIDED_AGAIN = (urls.c.fetch_state == literal_column("'queued'")) | (
    urls.c.skip_reason == literal_column("'max_depth'")
)
# A followed Link re-queues a URL skipped where it was found, through unfollowed Links or past
# the hop limit, as found through it, and gives the shorter path that a Checked URL found after
# its depth closed (design D3) to a URL still queued, or skipped beyond the depth limit, which
# dispatch then decides again. A Resource Link raises such a URL that a Link of another type
# recorded first, at its depth or a shorter one, so the Resource is requested. Every other
# conflict changes nothing, so a replayed unit gives the same rows (design D5).
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
            _literal_one_of(urls.c.skip_reason, literal_values(DiscoverySkipReason)),
            _DECIDED_AGAIN & (urls.c.crawl_depth > _INSERT.excluded.crawl_depth),
            _DECIDED_AGAIN
            & _literal_one_of(_INSERT.excluded.discovered_via, RESOURCE_LINK_TYPES)
            & ~_literal_one_of(urls.c.discovered_via, RESOURCE_LINK_TYPES)
            & (urls.c.crawl_depth >= _INSERT.excluded.crawl_depth),
        )
    )
    & (_INSERT.excluded.fetch_state == literal_column("'queued'")),
)
_URL_ID = select(urls.c.id).where(urls.c.url == bindparam("url"))
_SEED_HOP = select(urls.c.id, urls.c.url, urls.c.redirect_url_id).where(
    urls.c.url == bindparam("url")
)
_HOP = select(urls.c.id, urls.c.url, urls.c.redirect_url_id).where(urls.c.id == bindparam("url_id"))
_DEPTH = select(urls.c.crawl_depth).where(urls.c.id == bindparam("url_id"))
# Bound names differ from the columns: SQLAlchemy keeps a column's own name for its SET value.
_URL_ROW = update(urls).where(urls.c.id == bindparam("url_id"))
_RECLASSIFIED = _URL_ROW.values(is_internal=bindparam("internal"), in_scope=bindparam("scoped"))
_AT_THE_DISPATCHED_DEPTH = urls.c.crawl_depth == bindparam("dispatched_depth")
# What the dispatch acted on, unless a late check lowered the URL meanwhile (design D5).
_WRITE_BACK = {
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
    attempt_count=bindparam("attempts"),
    redirect_location=bindparam("location"),
    in_redirect_loop=bindparam("loop_flag"),
    parsed=bindparam("is_parsed"),
    parse_error=bindparam("parse_failure"),
    parse_error_message=bindparam("parse_failure_message"),
    body_truncated=bindparam("truncated"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_WRITE_BACK,
)
# Only on what the skip was decided on: a URL lowered or raised since then stays queued.
_SKIPPED = _URL_ROW.where(
    _AT_THE_DISPATCHED_DEPTH, urls.c.discovered_via == bindparam("dispatched_via")
).values(
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
    **_WRITE_BACK,
)
_UNWRITTEN = _URL_ROW.values(
    fetch_state="error",
    fetch_error="record_failed",
    fetch_error_message=bindparam("failure_message"),
    attempt_count=bindparam("attempts"),
    blocked_by_robots_txt=bindparam("robots_blocked"),
    **_WRITE_BACK,
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
    depth: int, after: int, size: int, max_redirects: int
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
                chain_via=chain_via(
                    connection, row.discovered_via, row.found_on_url_id, max_redirects
                ),
            )
            for row in rows
        )

    return unit


def seed_chain_urls(
    seed: NormalizedUrl, max_redirects: int
) -> Callable[[Connection], SeedChainUrls]:
    """A unit that only reads: the Seed's Redirect Chain as the file holds it, from the Seed
    along redirect_url_id, at most `max_redirects` + 1 hops; its last URL is the one it ends on,
    a target never requested included (022-add-fetch-policy D3)."""

    def unit(connection: Connection) -> SeedChainUrls:
        url_id, url, following = connection.execute(_SEED_HOP, {"url": seed}).one()
        chain = [(url_id, NormalizedUrl(url))]
        for _ in range(max_redirects + 1):
            if following is None or any(following == known for known, _ in chain):
                break
            url_id, url, following = connection.execute(_HOP, {"url_id": following}).one()
            chain.append((url_id, NormalizedUrl(url)))
        return tuple(chain)

    return unit


def next_depth(depth: int) -> Callable[[Connection], int | None]:
    """A unit that only reads: the shallowest depth deeper than `depth` with a queued URL."""

    def unit(connection: Connection) -> int | None:
        deeper: int | None = connection.execute(_NEXT_DEPTH, {"depth": depth}).scalar()
        return deeper

    return unit


def record_fetched(fetched: FetchedUrl) -> UrlUnit:
    """A unit that records the URL's response, the URLs discovered from it and its rows."""
    url_id, redirect = fetched.url_id, fetched.redirect
    values = {
        "url_id": url_id,
        "response_status": fetched.status_code,
        "response_type": fetched.content_type,
        "response_ms": fetched.response_time_ms,
        "attempts": fetched.attempt_count,
        "location": None if redirect is None else redirect.location,
        # 0 for any 3xx response until its redirect closes a loop.
        "loop_flag": None if redirect is None else False,
        "request_at": fetched.fetched_at,
        "is_parsed": fetched.parsed,
        "parse_failure": fetched.parse_error,
        "parse_failure_message": fetched.parse_error_message,
        "truncated": fetched.body_truncated,
        "robots_blocked": fetched.blocked_by_robots_txt,
        **_provenance_values(fetched.provenance),
    }
    new_rows = [_new_row(new, url_id) for new in fetched.discovered]

    target = None if redirect is None else redirect.target
    redirect_row = None if target is None else _new_row(target, url_id)
    max_redirects = 0 if redirect is None else redirect.max_redirects

    def unit(connection: Connection) -> bool:
        connection.execute(_FETCHED, values)
        if not new_rows and redirect_row is None:
            write_rows(connection, fetched.rows)
            return True
        # The stored depth, which a Checked URL answering late may have lowered while the URL
        # was in flight, so what it links to stays one deeper than it (design D3).
        depth: int = connection.execute(_DEPTH, {"url_id": url_id}).scalar_one()
        # The unique index urls_url is the only dedup: no URL map in memory (design D1).
        if new_rows:
            rows = [{**row, "crawl_depth": depth + 1} for row in new_rows]
            insert_urls(connection, _INSERT_DISCOVERED, rows)
        if redirect_row is not None:
            # A redirect is no Link: its target keeps the depth (022 design D2).
            row = {**redirect_row, "crawl_depth": depth}
            if past_the_hop_limit(connection, url_id, max_redirects):
                row |= {"fetch_state": "skipped", "skip_reason": "max_redirects"}
            insert_urls(connection, _INSERT_DISCOVERED, [row])
            target_id: int = connection.execute(_URL_ID, {"url": row["url"]}).scalar_one()
            link_redirect(connection, url_id, target_id, max_redirects)
        write_rows(connection, fetched.rows)
        return True

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


def reclassify_urls(decisions: Sequence[Reclassified]) -> UrlUnit:
    """A unit that writes is_internal and in_scope again, by URL id: the URLs of a Seed's
    Redirect Chain, against the Scope it ended in (022-add-fetch-policy D3)."""
    rows = [
        {"url_id": d.url_id, "internal": d.is_internal, "scoped": d.in_scope} for d in decisions
    ]

    def unit(connection: Connection) -> bool:
        connection.execute(_RECLASSIFIED, rows)
        return True

    return unit


def record_skipped(skipped: SkippedUrl) -> UrlUnit:
    """A unit that records a URL as not requested, why, and its rows, unless a shorter path
    lowered its depth after the skip was decided: it then stays queued (design D5)."""
    values = {
        "url_id": skipped.url_id,
        "reason": skipped.skip_reason,
        "robots_blocked": skipped.blocked_by_robots_txt,
        **_provenance_values(skipped.provenance),
    }

    def unit(connection: Connection) -> bool:
        if not connection.execute(_SKIPPED, values).rowcount:
            return False
        write_rows(connection, skipped.rows)
        return True

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
        **_provenance_values(errored.provenance),
    }

    def unit(connection: Connection) -> bool:
        connection.execute(_ERRORED, values)
        write_rows(connection, errored.rows)
        return True

    return unit


def record_unwritten(
    url_id: int,
    message: str,
    *,
    blocked_by_robots_txt: bool | None,
    attempt_count: int,
    provenance: Provenance,
) -> UrlUnit:
    """The fallback unit of a URL whose own unit failed: only its state, what robots.txt said
    of it, and the requests made for it (design D2)."""
    values = {
        "url_id": url_id,
        "failure_message": message,
        "robots_blocked": blocked_by_robots_txt,
        "attempts": attempt_count,
        **_provenance_values(provenance),
    }

    def unit(connection: Connection) -> bool:
        connection.execute(_UNWRITTEN, values)
        return True

    return unit


def _provenance_values(provenance: Provenance) -> dict[str, object]:
    return {
        "dispatched_depth": provenance.crawl_depth,
        "dispatched_via": provenance.discovered_via,
        "dispatched_found_on": provenance.found_on_url_id,
    }


def url_counts() -> Callable[[Connection], UrlCounts]:
    """A unit that only reads: the counts of a Crawl's result, from the rows (design D10)."""

    def unit(connection: Connection) -> UrlCounts:
        return UrlCounts(**connection.execute(_COUNTS).one()._mapping)

    return unit
