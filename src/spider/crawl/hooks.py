"""The hooks later changes plug into: extractors, handlers, passes (020-add-crawl-core D9)."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

import msgspec

from spider.crawl.pages import Extractor
from spider.crawl.urls import NormalizedUrl
from spider.store.records import DiscoveredVia, FetchError, FetchState, ParseError, SkipReason
from spider.store.rows import RowWriter
from spider.store.writer import CrawlWriter


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResult:
    """A URL that reached its final state: its row values, and its response when it got one."""

    url_id: int
    url: NormalizedUrl
    crawl_depth: int
    discovered_via: DiscoveredVia
    found_on_url_id: int | None
    is_internal: bool
    in_scope: bool
    fetch_state: FetchState
    skip_reason: SkipReason | None = None
    fetch_error: FetchError | None = None
    fetch_error_message: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    response_time_ms: int | None = None
    fetched_at: datetime | None = None
    parsed: bool = False
    parse_error: ParseError | None = None
    parse_error_message: str | None = None
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...] = ()
    # By extractor name, for a parsed response; an extractor that failed has none.
    outputs: Mapping[str, msgspec.Struct] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Handler:
    """Pure: the store rows for one URL, which its unit writes with the URL's final state."""

    name: str
    handle: Callable[[UrlResult], Iterable[object]]


@dataclass(frozen=True, slots=True)
class Pass:
    """A store function run once the last URL is recorded, before completed is written."""

    name: str
    run: Callable[[CrawlWriter], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class Hooks:
    extractors: tuple[Extractor, ...] = ()
    handlers: tuple[Handler, ...] = ()
    passes: tuple[Pass, ...] = ()
    # By row type: the store module that owns a table writes its rows (design D14).
    row_writers: Mapping[type, RowWriter] = field(default_factory=dict)
