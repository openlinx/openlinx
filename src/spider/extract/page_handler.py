"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable
from datetime import datetime

import msgspec

from spider.crawl.hooks import UrlResult
from spider.crawl.pages import is_html_type
from spider.extract.addresses import display_address, path_and_query
from spider.extract.cookies import cookie_row
from spider.extract.dates import internet_date
from spider.extract.page_data import page_data_of
from spider.store.page_records import CookieRow, PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    if not _is_page(result):
        return ()
    data = page_data_of(result.outputs)
    address = display_address(result.url)
    url_path, url_query = path_and_query(address)
    return (
        PageRow(
            url_id=result.url_id,
            address=address,
            url_encoded_address=result.url,
            url_path=url_path,
            url_query=url_query,
            content_type=_required(result.content_type, "content_type"),
            status_code=_required(result.status_code, "status_code"),
            response_time_ms=_required(result.response_time_ms, "response_time_ms"),
            last_modified=_last_modified(result.headers),
            set_cookie_count=sum(name.lower() == "set-cookie" for name, _ in result.headers),
            crawl_timestamp=_required(result.fetched_at, "fetched_at"),
            crawl_depth=result.crawl_depth,
            **({} if data is None else msgspec.structs.asdict(data)),
        ),
    )


def cookie_rows(result: UrlResult) -> Iterable[CookieRow]:
    if not _is_page(result):
        return ()
    values = [value for name, value in result.headers if name.lower() == "set-cookie"]
    return tuple(
        cookie_row(result.url_id, ordinal, value) for ordinal, value in enumerate(values, 1)
    )


def _required[T](value: T | None, name: str) -> T:
    # A fetched URL always has its response's values; the engine reports a handler that raises.
    if value is None:
        raise RuntimeError(f"a fetched URL has no {name}")
    return value


def _last_modified(headers: tuple[tuple[str, str], ...]) -> datetime | None:
    value = next((value for name, value in headers if name.lower() == "last-modified"), None)
    return None if value is None else internet_date(value)


def _is_page(result: UrlResult) -> bool:
    # The status code does not matter: a 404 or a 301 with an HTML body is a Page (design D2).
    return (
        result.is_internal
        and result.in_scope
        and result.fetch_state == "fetched"
        and is_html_type(result.content_type)
    )
