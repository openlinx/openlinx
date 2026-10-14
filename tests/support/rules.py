"""Crawl files that hold the rows a Rule reads, for seam-2 tests (040-add-rules, Test seams)."""

from collections.abc import Callable, Collection, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select

from spider.crawl.urls import NormalizedUrl
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.records import (
    ErroredUrl,
    FetchedUrl,
    FetchError,
    NewUrl,
    ParseError,
    RuleRow,
)
from spider.store.schema import urls
from spider.store.urls import record_error, record_fetched, record_seed, record_unwritten
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, default_rule_rows
from tests.support.workspace import TempWorkspace

_PAGE_URL = NormalizedUrl("https://site.test/")
_SEED = NormalizedUrl("https://example.test/")
_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
type UrlUnit = Callable[[Connection], None]


def crawl_with_page(
    temp_workspace: TempWorkspace,
    *,
    disabled: Collection[str] = (),
    parse_error: ParseError | None = None,
    more_rules: Sequence[RuleRow] = (),
    **page_data: Any,
) -> tuple[Path, int]:
    """A crawl file and the URL id of its one analysed Page, with these Page data columns,
    whose rules table marks the Rules named in `disabled` off; `extractor_error` as
    `parse_error` makes it a Page on which an extractor failed, and `more_rules` are
    recorded after the catalogue's Rules.

    The rows go through the store's own units, as a Crawl writes them: the Seed, then its
    HTML response with its Page row.
    """
    rules = (
        *(replace(rule, enabled=rule.id not in disabled) for rule in default_rule_rows()),
        *more_rules,
    )
    crawl = create_any_crawl(temp_workspace, rules=rules)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(_PAGE_URL, is_internal=True, in_scope=True))
        page = PageRow(url_id=url_id, address=_PAGE_URL, url_encoded_address=_PAGE_URL, **page_data)
        fetched = _html(url_id, parse_error=parse_error, rows=(page,))
        writer.run(record_fetched(fetched, {PageRow: write_page}))
    return crawl.path, url_id


def crawl_with_url(
    temp_workspace: TempWorkspace,
    url: str,
    outcome: Callable[[int], UrlUnit],
    *,
    is_internal: bool = True,
    in_scope: bool | None = None,
) -> tuple[Path, int]:
    """A crawl file whose Seed, https://example.test/, links to `url`, and the URL's id.

    `outcome` makes the unit that records how the URL's request ended, from its id, such as
    `responded(404)`; the rows go through the store's own units, as a Crawl writes them.
    The URL is in the Scope when it is Internal, unless `in_scope` says otherwise.
    """
    crawl = create_any_crawl(temp_workspace)
    target = NormalizedUrl(url)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(_SEED, is_internal=True, in_scope=True))
        found = NewUrl(
            url=target,
            crawl_depth=1,
            discovered_via="hyperlink",
            is_internal=is_internal,
            in_scope=is_internal if in_scope is None else in_scope,
        )
        writer.run(record_fetched(_html(seed_id, discovered=(found,)), {}))
        url_id = writer.run(_url_id(target))
        writer.run(outcome(url_id))
    return crawl.path, url_id


def responded(status_code: int) -> Callable[[int], UrlUnit]:
    """An outcome: the URL answered with this status, as a response that is not a Page."""
    return lambda url_id: record_fetched(
        FetchedUrl(
            url_id=url_id,
            status_code=status_code,
            content_type="text/plain",
            fetched_at=_AT,
            response_time_ms=1,
            parsed=False,
        ),
        {},
    )


def failed(fetch_error: FetchError) -> Callable[[int], UrlUnit]:
    """An outcome: the URL's request got no HTTP response, for this reason."""
    return lambda url_id: record_error(
        ErroredUrl(
            url_id=url_id,
            fetch_error=fetch_error,
            fetch_error_message=f"The request ended with {fetch_error}.",
            fetched_at=_AT,
        ),
        {},
    )


def unrecorded() -> Callable[[int], UrlUnit]:
    """An outcome: the Crawl got a response but failed to record it (record_failed)."""
    return lambda url_id: record_unwritten(url_id, "The URL's unit failed.")


def _html(
    url_id: int,
    *,
    discovered: tuple[NewUrl, ...] = (),
    rows: tuple[object, ...] = (),
    parse_error: ParseError | None = None,
) -> FetchedUrl:
    return FetchedUrl(
        url_id=url_id,
        status_code=200,
        content_type="text/html",
        fetched_at=_AT,
        response_time_ms=1,
        parsed=True,
        parse_error=parse_error,
        discovered=discovered,
        rows=rows,
    )


def _url_id(url: NormalizedUrl) -> Callable[[Connection], int]:
    def unit(connection: Connection) -> int:
        url_id: int = connection.execute(select(urls.c.id).where(urls.c.url == url)).scalar_one()
        return url_id

    return unit
