"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable

import msgspec

from spider.crawl.hooks import UrlResult
from spider.crawl.pages import is_html_type
from spider.extract.addresses import display_address
from spider.extract.page_data import PAGE_DATA
from spider.store.page_records import PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    if not _is_page(result):
        return ()
    data = result.outputs.get(PAGE_DATA.name)
    return (
        PageRow(
            url_id=result.url_id,
            address=display_address(result.url),
            url_encoded_address=result.url,
            **({} if data is None else msgspec.structs.asdict(data)),
        ),
    )


def _is_page(result: UrlResult) -> bool:
    # The status code does not matter: a 404 or a 301 with an HTML body is a Page (design D2).
    return (
        result.is_internal
        and result.in_scope
        and result.fetch_state == "fetched"
        and is_html_type(result.content_type)
    )
