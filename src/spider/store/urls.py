"""The units of the urls table: the frontier and each URL's outcome (020 D1, D2, D14)."""

from collections.abc import Callable, Sequence

from sqlalchemy import Connection, bindparam, func, literal_column, select, update
from sqlalchemy.dialects.sqlite import insert

from spider.crawl.urls import NormalizedUrl
from spider.store.records import NewUrl, QueuedUrl, UrlCounts
from spider.store.schema import urls

# Built once: units run once per URL (017-speed-up-crawl-writer D9).
_INSERT_URL = insert(urls).on_conflict_do_nothing(index_elements=[urls.c.url])
_URL_ID = select(urls.c.id).where(urls.c.url == bindparam("url"))
_FETCHED = (
    update(urls)
    .where(urls.c.id == bindparam("url_id"))
    .values(
        fetch_state="fetched",
        status_code=bindparam("response_status"),
        parsed=bindparam("is_parsed"),
    )
)
# A literal, as the partial index urls_crawl_depth_id is declared, so the frontier reads use it
# without the plan depending on a bound value (design D1).
_IS_QUEUED = urls.c.fetch_state == literal_column("'queued'")
_QUEUED = (
    select(urls.c.id, urls.c.url)
    .where(
        _IS_QUEUED,
        urls.c.crawl_depth == bindparam("depth"),
        urls.c.id > bindparam("after"),
    )
    .order_by(urls.c.id)
    .limit(bindparam("size"))
)
_STATUS = urls.c.status_code
_COUNTS = select(
    func.count().label("discovered"),
    func.count().filter(urls.c.fetch_state == "fetched").label("fetched"),
    func.count().filter(urls.c.fetch_state == "error").label("errors"),
    func.count().filter(urls.c.fetch_state == "skipped").label("skipped"),
    func.count().filter(_IS_QUEUED).label("queued"),
    func.count().filter(urls.c.parsed == 1).label("pages"),
    *(
        func.count().filter(_STATUS.between(low, low + 99)).label(f"status_{low // 100}xx")
        for low in (200, 300, 400, 500)
    ),
    func.count().filter(~_STATUS.between(200, 599)).label("status_other"),
)
_NEXT_DEPTH = select(func.min(urls.c.crawl_depth)).where(
    _IS_QUEUED, urls.c.crawl_depth > bindparam("depth")
)


def record_seed(url: NormalizedUrl, host: str) -> Callable[[Connection], int]:
    """A unit that records the Seed as queued, once, and returns its id."""

    def unit(connection: Connection) -> int:
        connection.execute(
            _INSERT_URL,
            {
                "url": url,
                "host": host,
                "crawl_depth": 0,
                "discovered_via": "seed",
                "fetch_state": "queued",
                "parsed": False,
            },
        )
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
        return tuple(QueuedUrl(row.id, NormalizedUrl(row.url)) for row in rows)

    return unit


def next_depth(depth: int) -> Callable[[Connection], int | None]:
    """A unit that only reads: the shallowest depth deeper than `depth` with a queued URL."""

    def unit(connection: Connection) -> int | None:
        deeper: int | None = connection.execute(_NEXT_DEPTH, {"depth": depth}).scalar()
        return deeper

    return unit


def record_fetched(
    url_id: int, status_code: int, *, parsed: bool, discovered: Sequence[NewUrl] = ()
) -> Callable[[Connection], None]:
    """A unit that records the URL's response and the URLs discovered from it."""
    new_rows = [
        {
            "url": new.url,
            "host": new.host,
            "crawl_depth": new.crawl_depth,
            "discovered_via": new.discovered_via,
            "found_on_url_id": url_id,
            "fetch_state": "queued",
            "parsed": False,
        }
        for new in discovered
    ]

    def unit(connection: Connection) -> None:
        connection.execute(
            _FETCHED, {"url_id": url_id, "response_status": status_code, "is_parsed": parsed}
        )
        # The unique index urls_url is the only dedup: no URL map in memory (design D1).
        if new_rows:
            connection.execute(_INSERT_URL, new_rows)

    return unit


def url_counts() -> Callable[[Connection], UrlCounts]:
    """A unit that only reads: the counts of a Crawl's result, from the rows (design D10)."""

    def unit(connection: Connection) -> UrlCounts:
        return UrlCounts(**connection.execute(_COUNTS).one()._mapping)

    return unit
