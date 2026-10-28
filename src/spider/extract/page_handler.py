"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable
from datetime import datetime

import msgspec

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import header_values
from spider.crawl.pages.preparation import is_html_type
from spider.extract.addresses import display_address, path_and_query
from spider.extract.cookies import cookie_row
from spider.extract.dates import internet_date
from spider.extract.page_data import PAGE_DATA
from spider.store.page_records import CookieRow, PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    page = _page_response(result)
    if page is None:
        return ()
    response, content_type = page
    data = PAGE_DATA.output(result.outputs)
    address = display_address(result.url)
    url_path, url_query = path_and_query(address)
    return (
        PageRow(
            url_id=result.url_id,
            address=address,
            url_encoded_address=result.url,
            url_path=url_path,
            url_query=url_query,
            content_type=content_type,
            status_code=response.status_code,
            response_time_ms=response.response_time_ms,
            last_modified=_last_modified(response.headers),
            set_cookie_count=len(header_values(response.headers, "Set-Cookie")),
            crawl_timestamp=response.fetched_at,
            **({} if data is None else msgspec.structs.asdict(data)),
        ),
    )


def cookie_rows(result: UrlResult) -> Iterable[CookieRow]:
    page = _page_response(result)
    if page is None:
        return ()
    response, _ = page
    return tuple(
        cookie_row(result.url_id, ordinal, value)
        for ordinal, value in enumerate(header_values(response.headers, "Set-Cookie"), 1)
    )


def _last_modified(headers: tuple[tuple[str, str], ...]) -> datetime | None:
    values = header_values(headers, "Last-Modified")
    return internet_date(values[0]) if values else None


def _page_response(result: UrlResult) -> tuple[UrlResponse, str] | None:
    # The status code does not matter: a 404 or a 301 with an HTML body is a Page (design D2).
    response = result.response
    if response is None or not (result.is_internal and result.in_scope):
        return None
    content_type = response.content_type
    if content_type is None or not is_html_type(content_type):
        return None
    return response, content_type
