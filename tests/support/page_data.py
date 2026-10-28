"""Page data at seam 4: page preparation, then the Page handler (030-add-page-data, Test seams)."""

from datetime import UTC, datetime

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import FetchResult
from spider.crawl.pages.preparation import (
    PageSettings,
    prepare_page,
    response_directives,
    response_links,
)
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl
from spider.extract.content_area import ContentArea
from spider.extract.page_data import PAGE_DATA, page_data_extractor
from spider.extract.page_handler import page_rows
from spider.naming import DEFAULT_ROBOTS_TOKEN
from spider.services.hooks import default_hooks
from spider.store.page_records import PageRow

_URL = NormalizedUrl("https://site.test/")
# The spec's fixture A, which later scenarios refer to.
FIXTURE_A = """<html lang="en"><head><title>Hello</title></head><body>
<header><p>Site header text</p></header>
<nav><a href="/">Home</a></nav>
<main><h1>Welcome</h1><p>Reading is fun. Water is wet.</p></main>
<footer><p>Footer text</p></footer>
</body></html>"""


def page_row(
    html: str | bytes,
    content_type: str = "text/html; charset=utf-8",
    content_area: ContentArea | None = None,
    headers: tuple[tuple[str, str], ...] = (),
    url: str = _URL,
) -> PageRow:
    """The Page row of an analysed Page with this body and these headers besides its
    Content-Type, through the built-in extractors, the Page extractor's config being
    `content_area` when it is given. Its Links are the engine's: the headers', then the
    document's."""
    body = html.encode() if isinstance(html, str) else html
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", content_type), *headers),
        body=body,
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        response_time_ms=1,
    )
    extractors = default_hooks().extractors
    if content_area is not None:
        page_data = page_data_extractor(content_area)
        extractors = tuple(
            page_data if built.name == PAGE_DATA.name else built for built in extractors
        )
    page_url = NormalizedUrl(url)
    scope = scope_rules(page_url)
    settings = PageSettings(scope=scope, extractors=extractors, strip_params=None)
    prepared = prepare_page(page_url, response, settings)
    assert prepared.parse_error is None, prepared.parse_error_message
    result = UrlResult(
        url_id=1,
        url=page_url,
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
        links=response_links(page_url, response, scope, None) + prepared.html_links,
        outputs=dict(prepared.outputs),
    )
    (row,) = page_rows(result)
    return row


def unprepared_page_row(headers: tuple[tuple[str, str], ...], url: str = _URL) -> PageRow:
    """The Page row of a 200 HTML response that page preparation gave nothing for, such as one
    whose body was too large: the crawl engine still reads its headers' directives and Links."""
    page_url = NormalizedUrl(url)
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", "text/html"), *headers),
        body=b"",
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        response_time_ms=1,
    )
    result = UrlResult(
        url_id=1,
        url=page_url,
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        response=UrlResponse(
            status_code=200,
            reason="OK",
            content_type="text/html",
            headers=response.headers,
            fetched_at=response.fetched_at,
            response_time_ms=1,
            directives=response_directives(response, DEFAULT_ROBOTS_TOKEN),
        ),
        parsed=False,
        parse_error="body_too_large",
        links=response_links(page_url, response, scope_rules(page_url), None),
    )
    (row,) = page_rows(result)
    return row
