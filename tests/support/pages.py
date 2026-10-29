"""A document's Links, as page preparation reads them from a 200 response (seam 4)."""

from datetime import UTC, datetime

from spider.crawl.fetch.fetcher import FetchResult
from spider.crawl.pages.preparation import PageSettings, prepare_page
from spider.crawl.references import DiscoveredLink
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl


def page_links(
    body: bytes, content_type: str | None, url: NormalizedUrl, *, follow_nofollow: bool = False
) -> tuple[DiscoveredLink, ...]:
    """The Scope is the URL's own, as a Crawl of it would have."""
    headers = () if content_type is None else (("Content-Type", content_type),)
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=headers,
        body=body,
        fetched_at=datetime(2026, 10, 27, tzinfo=UTC),
        response_time_ms=1,
    )
    settings = PageSettings(
        scope=scope_rules(url), strip_params=None, follow_nofollow=follow_nofollow
    )
    return prepare_page(url, response, settings).html_links
