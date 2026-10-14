"""The hooks later changes plug into: handlers, passes and row writers (020-add-crawl-core D9)."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from spider.crawl.urls import NormalizedUrl
from spider.store.records import FetchState, SkipReason
from spider.store.rows import RowWriter
from spider.store.writer import CrawlWriter


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlResult:
    """A URL that reached its final state: its row values, and its response when it got one."""

    url_id: int
    url: NormalizedUrl
    crawl_depth: int
    fetch_state: FetchState
    skip_reason: SkipReason | None = None
    status_code: int | None = None
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Handler:
    """Pure: the store rows for one URL, which its unit writes with the URL's final state."""

    name: str
    handle: Callable[[UrlResult], Sequence[object]]


@dataclass(frozen=True, slots=True)
class Pass:
    """A store function run once the last URL is recorded, before completed is written."""

    name: str
    run: Callable[[CrawlWriter], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class Hooks:
    handlers: tuple[Handler, ...] = ()
    passes: tuple[Pass, ...] = ()
    # By row type: the store module that owns a table writes its rows (design D14).
    row_writers: Mapping[type, RowWriter] = field(default_factory=dict)


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks()
