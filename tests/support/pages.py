"""A document's Links, as page preparation reads them from a 200 response (seam 4), and a page
executor that holds Pages beyond the requests in flight, as 026's pool does."""

from datetime import UTC, datetime

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import PageSettings, PreparedPage, prepare_page
from openlinx.crawl.references import DiscoveredLink
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl


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


class BackloggedPool:
    """A page executor that may hold `backlog` Pages beyond the requests in flight, as 026's
    pool does, and prepares each one at once; pass it as `pages=lambda: BackloggedPool(2)`."""

    workers = 1

    def __init__(self, backlog: int) -> None:
        self.backlog = backlog
        self._settings: PageSettings | None = None

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        assert self._settings is not None
        return prepare_page(url, response, self._settings)

    async def close(self) -> None:
        pass
