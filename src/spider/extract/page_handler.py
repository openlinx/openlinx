"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable

from spider.crawl.hooks import UrlResult
from spider.store.page_records import PageRow


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    return (PageRow(url_id=result.url_id, address=result.url),)
