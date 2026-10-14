"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable

from spider.crawl.hooks import UrlResult
from spider.crawl.pages import is_html_type
from spider.extract.addresses import display_address
from spider.store.page_records import PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    if not is_html_type(result.content_type):
        return ()
    return (
        PageRow(
            url_id=result.url_id,
            address=display_address(result.url),
            url_encoded_address=result.url,
        ),
    )
