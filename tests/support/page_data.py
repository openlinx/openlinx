"""Page data at seam 4: page preparation, then the Page handler (030-add-page-data, Test seams)."""

from datetime import UTC, datetime

from openlinx.crawl.engine.hooks import UrlResponse, UrlResult
from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import (
    PageSettings,
    prepare_page,
    response_directives,
    response_links,
)
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.extract.content_area import ContentArea
from openlinx.extract.link_handler import link_rows
from openlinx.extract.page_data import PAGE_DATA, page_data_extractor
from openlinx.extract.page_handler import page_rows
from openlinx.extract.status_phrases import STATUS_PHRASES
from openlinx.naming import DEFAULT_ROBOTS_TOKEN
from openlinx.services.hooks import default_hooks
from openlinx.store.page_records import LinkRow, PageRow

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
    status_code: int = 200,
) -> PageRow:
    """The Page row of an analysed Page with this body and these headers besides its
    Content-Type, through the built-in extractors, the Page extractor's config being
    `content_area` when it is given. Its Links are the engine's: the headers', then the
    document's."""
    (row,) = page_rows(page_result(html, content_type, content_area, headers, url, status_code))
    return row


def page_link_rows(
    html: str | bytes, headers: tuple[tuple[str, str], ...] = (), url: str = _URL
) -> tuple[LinkRow, ...]:
    """The Link rows of an analysed Page, as page_row builds it."""
    return tuple(link_rows(page_result(html, headers=headers, url=url)))


def page_result(
    html: str | bytes,
    content_type: str = "text/html; charset=utf-8",
    content_area: ContentArea | None = None,
    headers: tuple[tuple[str, str], ...] = (),
    url: str = _URL,
    status_code: int = 200,
) -> UrlResult:
    # The crawl engine prepares only a 2xx response; another status is unprepared_page_row's.
    assert 200 <= status_code < 300, status_code
    body = html.encode() if isinstance(html, str) else html
    response = FetchResult(
        status_code=status_code,
        reason=STATUS_PHRASES[status_code],
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
    return UrlResult(
        url_id=1,
        url=page_url,
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        blocked_by_robots_txt=False,
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


def response_link_rows(
    content_type: str, headers: tuple[tuple[str, str], ...] = (), url: str = _URL
) -> tuple[LinkRow, ...]:
    """The Link rows of an in-Scope 200 response that is not HTML, such as a PDF, built as the
    crawl engine builds its result: its header Links, and no extractor output."""
    page_url = NormalizedUrl(url)
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", content_type), *headers),
        body=b"%PDF-1.7",
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
        blocked_by_robots_txt=False,
        response=UrlResponse(
            status_code=200,
            reason="OK",
            content_type=content_type,
            headers=response.headers,
            fetched_at=response.fetched_at,
            response_time_ms=1,
            directives=response_directives(response, DEFAULT_ROBOTS_TOKEN),
        ),
        links=response_links(page_url, response, scope_rules(page_url), None),
    )
    return tuple(link_rows(result))


def unprepared_page_row(
    headers: tuple[tuple[str, str], ...] = (),
    url: str = _URL,
    status_code: int = 200,
    blocked_by_robots_txt: bool | None = False,
) -> PageRow:
    """The Page row of an HTML response that page preparation gave nothing for, built as the
    crawl engine builds it: the directives of its headers, and its header Links only when it is
    2xx. The engine prepares no other status, and a 2xx one gives nothing when its body was too
    large."""
    page_url = NormalizedUrl(url)
    response = FetchResult(
        status_code=status_code,
        reason=STATUS_PHRASES.get(status_code, ""),
        headers=(("Content-Type", "text/html"), *headers),
        body=b"",
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        response_time_ms=1,
    )
    followed = 200 <= status_code < 300
    result = UrlResult(
        url_id=1,
        url=page_url,
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        blocked_by_robots_txt=blocked_by_robots_txt,
        response=UrlResponse(
            status_code=status_code,
            reason=response.reason,
            content_type="text/html",
            headers=response.headers,
            fetched_at=response.fetched_at,
            response_time_ms=1,
            directives=response_directives(response, DEFAULT_ROBOTS_TOKEN),
        ),
        parsed=False,
        parse_error="body_too_large" if followed else None,
        links=response_links(page_url, response, scope_rules(page_url), None) if followed else (),
    )
    (row,) = page_rows(result)
    return row
