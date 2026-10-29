"""The hooks later changes plug into: extractors, handlers, passes (020-add-crawl-core D9)."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import msgspec

from openlinx.clock import Clock
from openlinx.crawl.pages.directives import RobotsDirectives
from openlinx.crawl.pages.preparation import Extractor
from openlinx.crawl.references import DiscoveredLink
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import DiscoveredVia, FetchError, FetchState, ParseError, SkipReason
from openlinx.store.rows import RowWriter
from openlinx.store.writer import CrawlWriter


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResponse:
    """The URL's own HTTP response."""

    status_code: int
    # The status line's reason phrase, as received.
    reason: str | None
    # The Content-Type header as received; None without one.
    content_type: str | None
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    fetched_at: datetime
    response_time_ms: int
    # Page preparation's when the Page was parsed, else the X-Robots-Tag's alone.
    directives: RobotsDirectives


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

    def __post_init__(self) -> None:
        # Outputs are keyed by the extractor's name, so a second extractor of a name would
        # silently replace the first's output (design D9).
        _refuse_twice("extractors", [extractor.name for extractor in self.extractors])
        _refuse_twice("handlers", [handler.name for handler in self.handlers])


def _refuse_twice(kind: str, names: list[str]) -> None:
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise TypeError(f"two {kind} named {', '.join(twice)}: give each its own name")
