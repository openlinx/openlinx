"""Define extractor, handler and pass contracts without importing their implementations."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import msgspec

from openlinx.clock import Clock
from openlinx.crawl.pages.directives import RobotsDirectives
from openlinx.crawl.pages.preparation import Extractor
from openlinx.crawl.references import DiscoveredLink
from openlinx.crawl.urls import NormalizedUrl
from openlinx.store.records import DiscoveredVia, FetchError, FetchState, ParseError, SkipReason
from openlinx.store.rows import RowWriter
from openlinx.store.writer import Unit


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResponse:
    status_code: int
    # The status line's reason phrase, as received.
    reason: str | None
    # The Content-Type header as received; None without one.
    content_type: str | None
    # As received, cookie values redacted (openlinx.crawl.fetch.cookies): in order, in their letter
    # case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    fetched_at: datetime
    response_time_ms: int
    # Reading stopped because the transferred body or a decoding stage exceeded the cap.
    body_truncated: bool
    # Content-Encoding field values joined in arrival order, or None if absent.
    content_encoding: str | None
    # Complete decoded body size, or None on truncation or unsupported coding.
    size_bytes: int | None
    # Includes the full last chunk read. None when the Fetcher did not measure it.
    transferred_bytes: int | None
    # Page preparation's when the Page was parsed, else the X-Robots-Tag's alone.
    directives: RobotsDirectives
    # For a 301, 302, 303, 307 or 308, the Location resolved to an HTTP(S) URL.
    # None for other statuses or when Location gives no such URL.
    redirect_target: NormalizedUrl | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlFailure:
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
    # NULL when robots.txt was not checked.
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
    # then its document's when it was prepared.
    links: tuple[DiscoveredLink, ...] = ()
    # By extractor name, for a parsed response; an extractor that failed has none. A handler
    # reads one with that extractor's output(outputs).
    outputs: Mapping[str, msgspec.Struct] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Handler[R]:
    """Pure: one table's rows for one URL, which its unit writes with the URL's final state
    through the store function that owns the table; two tables are two handlers
    (020-add-crawl-core D9)."""

    name: str
    handle: Callable[[UrlResult], Iterable[R]]
    write: RowWriter[R]


def handler[R](
    name: str, handle: Callable[[UrlResult], Iterable[R]], write: RowWriter[R]
) -> Handler[Any]:
    """The one way to build a handler: mypy checks R here, where the handler is registered,
    since a Handler built in place inside Hooks(...) takes R as Any (020-add-crawl-core D9)."""
    return Handler(name, handle, write)


class PassWriter(Protocol):
    """Async submission wakes the loop's commit timer, and a pass can flush without waiting
    for that timer. The Crawl closes its writer (023-fix-code-audit D5)."""

    async def run_async[T](self, unit: Unit[T]) -> T: ...

    async def submit_async[T](self, unit: Unit[T]) -> asyncio.Future[T]: ...

    async def flush_async(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PassContext:
    """What a post-crawl pass gets: a later dependency is a new field, not a new signature."""

    writer: PassWriter
    clock: Clock


@dataclass(frozen=True, slots=True)
class Pass:
    """An async hook run after URL processing, before the Crawl records completed or stopped.
    A continued run can execute the hook again (020-add-crawl-core D9)."""

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
        # silently replace the first's output.
        _refuse_twice("extractors", [extractor.name for extractor in self.extractors])
        _refuse_twice("handlers", [handler.name for handler in self.handlers])


def _refuse_twice(kind: str, names: list[str]) -> None:
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise TypeError(f"two {kind} named {', '.join(twice)}: give each its own name")
