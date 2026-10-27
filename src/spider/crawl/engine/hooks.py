"""The hooks later changes plug into: extractors, handlers, passes (020-add-crawl-core D9)."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import msgspec

from spider.clock import Clock
from spider.crawl.pages.directives import RobotsDirectives
from spider.crawl.pages.preparation import Extractor
from spider.crawl.references import DiscoveredLink
from spider.crawl.urls import NormalizedUrl
from spider.store.records import DiscoveredVia, FetchError, FetchState, ParseError, SkipReason
from spider.store.rows import RowWriter
from spider.store.writer import CrawlWriter


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResponse:
    """The URL's own HTTP response."""

    status_code: int
    # The status line's reason phrase, as received.
    reason: str | None
    # The Content-Type header as received; None without one.
    content_type: str | None
    # As received, cookie values redacted (spider.crawl.fetch.cookies): in order, in their letter
    # case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    fetched_at: datetime
    response_time_ms: int
    # Larger than the body cap, so read only up to it (022 design D1).
    body_truncated: bool
    # The Content-Encoding header as received; None without one.
    content_encoding: str | None
    # The body after decoding, and as transferred; None where not measured (022 design D1).
    size_bytes: int | None
    transferred_bytes: int | None
    # Page preparation's when the Page was parsed, else the X-Robots-Tag's alone.
    directives: RobotsDirectives
    # Where a 301, 302, 303, 307 or 308 leads; None for any other response (022 design D2).
    redirect_target: NormalizedUrl | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlFailure:
    """Why the URL has no response."""

    fetch_error: FetchError
    fetch_error_message: str
    # None without a request of its own: its origin's robots.txt got no response.
    fetched_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResult:
    """A URL that reached its final state: its row values and its outcome's record."""

    url_id: int
    url: NormalizedUrl
    crawl_depth: int
    discovered_via: DiscoveredVia
    found_on_url_id: int | None
    is_internal: bool
    in_scope: bool
    fetch_state: FetchState
    # NULL when robots.txt was not checked (design D6).
    blocked_by_robots_txt: bool | None = None
    # The requests made for the URL, retries included; 0 when it was not requested.
    attempt_count: int = 0
    skip_reason: SkipReason | None = None
    # A fetched URL has a response, an errored one a failure, a skipped one neither.
    response: UrlResponse | None = None
    failure: UrlFailure | None = None
    parsed: bool = False
    parse_error: ParseError | None = None
    parse_error_message: str | None = None
    # The Links the engine read for discovery: an in-Scope 2xx response's header Links,
    # then its document's when it was prepared (design D5).
    links: tuple[DiscoveredLink, ...] = ()
    # By extractor name, for a parsed response; an extractor that failed has none. A handler
    # reads one with that extractor's output(outputs).
    outputs: Mapping[str, msgspec.Struct] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Handler[R]:
    """Pure: one table's rows for one URL, which its unit writes with the URL's final state
    through the store function that owns the table; two tables are two handlers (design D9)."""

    name: str
    handle: Callable[[UrlResult], Iterable[R]]
    write: RowWriter[R]


def handler[R](
    name: str, handle: Callable[[UrlResult], Iterable[R]], write: RowWriter[R]
) -> Handler[Any]:
    """The one way to build a handler: mypy checks R here, where the handler is registered,
    since a Handler built in place inside Hooks(...) takes R as Any (design D9)."""
    return Handler(name, handle, write)


@dataclass(frozen=True, slots=True)
class PassContext:
    """What a post-crawl pass gets: a later dependency is a new field, not a new signature."""

    writer: CrawlWriter
    clock: Clock


@dataclass(frozen=True, slots=True)
class Pass:
    """A store function run once the last URL is recorded, before completed is written."""

    name: str
    run: Callable[[PassContext], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class Hooks:
    extractors: tuple[Extractor[Any, Any], ...] = ()
    handlers: tuple[Handler[Any], ...] = ()
    # One after another in this order, so a pass may read what an earlier one wrote.
    passes: tuple[Pass, ...] = ()
