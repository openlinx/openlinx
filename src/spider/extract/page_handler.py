"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import msgspec

from spider.crawl.hooks import UrlResult
from spider.crawl.pages import is_html_type
from spider.extract.addresses import display_address, path_and_query
from spider.extract.page_data import PAGE_DATA
from spider.store.page_records import PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    if not _is_page(result):
        return ()
    data = result.outputs.get(PAGE_DATA.name)
    address = display_address(result.url)
    url_path, url_query = path_and_query(address)
    return (
        PageRow(
            url_id=result.url_id,
            address=address,
            url_encoded_address=result.url,
            url_path=url_path,
            url_query=url_query,
            last_modified=_last_modified(result.headers),
            **({} if data is None else msgspec.structs.asdict(data)),
        ),
    )


def _last_modified(headers: tuple[tuple[str, str], ...]) -> datetime | None:
    value = next((value for name, value in headers if name.lower() == "last-modified"), None)
    if value is None:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except ValueError:
        return None
    # An HTTP-date is always GMT, also in the asctime form, which names no zone.
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _is_page(result: UrlResult) -> bool:
    # The status code does not matter: a 404 or a 301 with an HTML body is a Page (design D2).
    return (
        result.is_internal
        and result.in_scope
        and result.fetch_state == "fetched"
        and is_html_type(result.content_type)
    )
