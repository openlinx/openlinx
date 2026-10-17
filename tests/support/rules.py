"""Crawl files that hold the rows a Rule reads, for seam-2 tests (040-add-rules, Test seams)."""

from collections.abc import Callable, Collection, Mapping, Sequence
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
from spider.store.rows import HandlerRows
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
# The Page data of two Pages whose titles are the same.
SHOES: Mapping[str, Any] = {"title_count": 1, "title_1": "Shoes", "title_1_length": 5}


def crawl_with_page(
    temp_workspace: TempWorkspace,
    *,
    disabled: Collection[str] = (),
    parse_error: ParseError | None = None,
    more_rules: Sequence[RuleRow] = (),
    thresholds: Mapping[str, Mapping[str, int]] | None = None,
    **page_data: Any,
) -> tuple[Path, int]:
    """A crawl file and the URL id of its one analysed Page, with these Page data columns,
    whose rules table marks the Rules named in `disabled` off and records the
    `thresholds` given by Rule id as a spider.toml would; `extractor_error` as
    `parse_error` makes it a Page on which an extractor failed, any other parse error a
    Page that was not parsed, and `more_rules` are
    recorded after the catalogue's Rules.

    The rows go through the store's own units, as a Crawl writes them: the Seed, then its
    HTML response with its Page row.
    """
    rules = (
        *(
            replace(
                rule,
                enabled=rule.id not in disabled,
                thresholds={**rule.thresholds, **(thresholds or {}).get(rule.id, {})},
            )
            for rule in default_rule_rows()
        ),
        *more_rules,
    )
    crawl = create_any_crawl(temp_workspace, rules=rules)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(_PAGE_URL, is_internal=True, in_scope=True))
        page = PageRow(url_id=url_id, address=_PAGE_URL, url_encoded_address=_PAGE_URL, **page_data)
        fetched = _html(url_id, parse_error=parse_error, rows=(HandlerRows(write_page, (page,)),))
        writer.run(record_fetched(fetched))
    return crawl.path, url_id


def crawl_with_pages(
    temp_workspace: TempWorkspace,
    *pages: Mapping[str, Any],
    parse_error: ParseError | None = None,
) -> tuple[Path, list[int]]:
    """A crawl file of Pages with these Page data columns, and their URL ids: the Seed,
    https://site.test/, then /2, /3 and on, which it links to; each with `parse_error`, as
    crawl_with_page takes it."""
    crawl = create_any_crawl(temp_workspace)
    urls = [NormalizedUrl(_PAGE_URL + (str(n) if n > 1 else "")) for n in range(1, len(pages) + 1)]
    found = tuple(
        NewUrl(url=url, discovered_via="hyperlink", is_internal=True, in_scope=True)
        for url in urls[1:]
    )
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(urls[0], is_internal=True, in_scope=True))
        writer.run(
            record_fetched(
                _html(
                    seed_id,
                    discovered=found,
                    rows=_page(seed_id, urls[0], pages[0]),
                    parse_error=parse_error,
                )
            )
        )
        ids = [seed_id]
        for url, page_data in zip(urls[1:], pages[1:], strict=True):
            ids.append(writer.run(_url_id(url)))
            rows = _page(ids[-1], url, page_data)
            writer.run(record_fetched(_html(ids[-1], rows=rows, parse_error=parse_error)))
    return crawl.path, ids


def _page(
    url_id: int, url: NormalizedUrl, page_data: Mapping[str, Any]
) -> tuple[HandlerRows[Any], ...]:
    page = PageRow(url_id=url_id, address=url, url_encoded_address=url, **page_data)
    return (HandlerRows(write_page, (page,)),)


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
            discovered_via="hyperlink",
            is_internal=is_internal,
            in_scope=is_internal if in_scope is None else in_scope,
        )
        writer.run(record_fetched(_html(seed_id, discovered=(found,))))
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
        )
    )


def failed(fetch_error: FetchError) -> Callable[[int], UrlUnit]:
    """An outcome: the URL's request got no HTTP response, for this reason."""
    return lambda url_id: record_error(
        ErroredUrl(
            url_id=url_id,
            fetch_error=fetch_error,
            fetch_error_message=f"The request ended with {fetch_error}.",
            fetched_at=_AT,
        )
    )


def unrecorded() -> Callable[[int], UrlUnit]:
    """An outcome: the Crawl got a response but failed to record it (record_failed)."""
    return lambda url_id: record_unwritten(
        url_id, "The URL's unit failed.", blocked_by_robots_txt=None
    )


def _html(
    url_id: int,
    *,
    discovered: tuple[NewUrl, ...] = (),
    rows: tuple[HandlerRows[Any], ...] = (),
    parse_error: ParseError | None = None,
) -> FetchedUrl:
    return FetchedUrl(
        url_id=url_id,
        status_code=200,
        content_type="text/html",
        fetched_at=_AT,
        response_time_ms=1,
        parsed=parse_error in (None, "extractor_error"),
        parse_error=parse_error,
        discovered=discovered,
        rows=rows,
    )


def _url_id(url: NormalizedUrl) -> Callable[[Connection], int]:
    def unit(connection: Connection) -> int:
        url_id: int = connection.execute(select(urls.c.id).where(urls.c.url == url)).scalar_one()
        return url_id

    return unit
