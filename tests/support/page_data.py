"""Page data at seam 4: page preparation, then the Page handler (030-add-page-data, Test seams)."""

from datetime import UTC, datetime

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import FetchResult
from spider.crawl.pages.preparation import PageSettings, extractor, prepare_page
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl
from spider.extract.content import ContentArea
from spider.extract.page_data import PAGE_DATA, extract_page_data
from spider.extract.page_handler import page_rows
from spider.services.hooks import default_hooks
from spider.store.page_records import PageRow

_URL = NormalizedUrl("https://site.test/")


def page_row(
    html: str | bytes,
    content_type: str = "text/html; charset=utf-8",
    content_area: ContentArea | None = None,
) -> PageRow:
    """The Page row of an analysed Page with this body, through the built-in extractors, the
    Page extractor's config being `content_area` when it is given."""
    body = html.encode() if isinstance(html, str) else html
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", content_type),),
        body=body,
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        response_time_ms=1,
    )
    extractors = default_hooks().extractors
    if content_area is not None:
        page_data = extractor(PAGE_DATA.name, extract_page_data, content_area)
        extractors = tuple(page_data if e.name == PAGE_DATA.name else e for e in extractors)
    settings = PageSettings(scope=scope_rules(_URL), extractors=extractors, strip_params=None)
    prepared = prepare_page(_URL, response, settings)
    assert prepared.parse_error is None, prepared.parse_error_message
    result = UrlResult(
        url_id=1,
        url=_URL,
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        response=UrlResponse(
            status_code=response.status_code,
            reason=response.reason,
            content_type=content_type,
            headers=response.headers,
            fetched_at=response.fetched_at,
            response_time_ms=response.response_time_ms,
            directives=prepared.directives,
        ),
        parsed=True,
        outputs=dict(prepared.outputs),
    )
    (row,) = page_rows(result)
    return row
