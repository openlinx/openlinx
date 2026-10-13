"""The urls table's units (020-add-crawl-core D1, D2, D14)."""

from collections.abc import Callable

from sqlalchemy import Connection, bindparam, select, update
from sqlalchemy.dialects.sqlite import insert

from spider.crawl.urls import NormalizedUrl
from spider.store.schema import urls

# Built once: units run once per URL (017-speed-up-crawl-writer D9).
_INSERT_URL = insert(urls).on_conflict_do_nothing(index_elements=[urls.c.url])
_URL_ID = select(urls.c.id).where(urls.c.url == bindparam("url"))
_FETCHED = (
    update(urls)
    .where(urls.c.id == bindparam("url_id"))
    .values(fetch_state="fetched", status_code=bindparam("response_status"))
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
            },
        )
        url_id: int = connection.execute(_URL_ID, {"url": url}).scalar_one()
        return url_id

    return unit


def record_fetched(url_id: int, status_code: int) -> Callable[[Connection], None]:
    """A unit that records the URL's response."""

    def unit(connection: Connection) -> None:
        connection.execute(_FETCHED, {"url_id": url_id, "response_status": status_code})

    return unit
