"""The store's records and enumerations, loading no sqlalchemy (designs D6 and D9 of 015)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from spider.crawl.urls import NormalizedUrl
from spider.workspace.discovery import Workspace

type CrawlMode = Literal["spider", "list", "sitemap"]

# A plain alias, not a type statement: Typer reads it as the choices of --scope.
ScopeKind = Literal["host", "subdomains", "subfolder"]


class RecordedScope(TypedDict):
    """crawl.scope (020-add-crawl-core D18)."""

    mode: ScopeKind
    hosts: list[str]
    folder: str | None
    include: list[str]
    exclude: list[str]


type JournalMode = Literal["wal", "delete"]
type JournalSetting = Literal["auto", "wal", "delete"]
type CrawlState = Literal["running", "stopped", "completed", "failed", "interrupted"]
# Why a Crawl or one of its runs ended early; the one value set of every such column (D12).
type StopReason = Literal[
    "max_urls", "interrupt", "requested", "seed_unreachable", "site_unreachable", "write_failed"
]
# Rules applied, everything allowed, or everything disallowed or unanswered (D6).
type RobotsState = Literal["ok", "missing", "unreachable"]
type SkipReason = Literal[
    "excluded",
    "blocked_by_robots_txt",
    "robots_unreachable",
    "nofollow",
    "link_type_not_followed",
    "external_not_checked",
    "max_depth",
    "max_redirects",
    "url_too_long",
]
# The reasons a URL is recorded as skipped when it is discovered, never dispatched; a later
# followed Link re-queues a URL skipped for one of them (020 D5).
type DiscoverySkipReason = Literal["nofollow", "link_type_not_followed"]
type LinkType = Literal[
    "hyperlink",
    "canonical",
    "pagination",
    "hreflang",
    "iframe",
    "meta_refresh",
    "http_refresh",
    "image",
    "css",
    "javascript",
    "video",
    "audio",
    "media",
    "amphtml",
    "mobile_alternate",
    "misc",
    "xml_sitemap",
    "sitemap_hreflang",
    "javascript_redirect",
]
type DeclaredIn = Literal["html", "http_header"]
type DiscoveredVia = (
    Literal["seed"] | LinkType | Literal["redirect", "list", "sitemap_input", "sitemap_index"]
)
type FetchState = Literal["queued", "fetched", "error", "skipped"]
type FetchError = Literal[
    "dns_error",
    "connection_refused",
    "connection_error",
    "invalid_response",
    "watchdog",
    "record_failed",
    "timeout",
    "tls_error",
]
# extractor_error keeps parsed = 1; the others mean nothing came out of page preparation.
type ParseError = Literal["extractor_error", "body_too_large", "worker_crashed", "parse_timeout"]

# The --crawl value that selects the Crawl that started last.
LATEST = "latest"


@dataclass(frozen=True)
class SecretNames:
    """The secret flags, such as --token, and secret settings, such as example.token."""

    flags: frozenset[str] = frozenset()
    settings: frozenset[str] = frozenset()


@dataclass(frozen=True, kw_only=True)
class NewCrawl:
    workspace: Workspace
    crawl_mode: CrawlMode
    seeds: Sequence[str]
    command_argv: Sequence[str]
    cwd: Path
    config: Mapping[str, Any]
    scope: RecordedScope
    # No defaults: a creator that forgot its secrets would record them, and one that forgot the
    # store.journal_mode setting would silently ignore it.
    secret_names: SecretNames
    journal_setting: JournalSetting
    section_crawl: bool
    settings_file: Path | None = None


@dataclass(frozen=True)
class CrawlFile:
    id: str
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class QueuedUrl:
    """A URL the frontier hands to the engine, with the row values its handlers get."""

    id: int
    url: NormalizedUrl
    crawl_depth: int
    discovered_via: DiscoveredVia
    found_on_url_id: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewUrl:
    """A URL discovered from a response, recorded unless the Crawl has it already, one
    deeper than the URL it was found on as the store holds it (design D3)."""

    url: NormalizedUrl
    discovered_via: DiscoveredVia
    is_internal: bool
    in_scope: bool
    # Why none of the Page's Links to it is followed; None queues it (design D5).
    skip_reason: DiscoverySkipReason | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UrlCounts:
    """The urls counts of a Crawl's result, by fetch_state, by parsed and by status class."""

    discovered: int
    fetched: int
    errors: int
    skipped: int
    queued: int
    pages: int
    status_2xx: int
    status_3xx: int
    status_4xx: int
    status_5xx: int
    status_other: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CrawlSummary:
    """What a Crawl's result reports from its crawl and seeds rows."""

    state: CrawlState
    stop_reason: StopReason | None
    crawl_mode: CrawlMode
    section_crawl: bool
    started_at: str
    seed: str
    seed_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchedUrl:
    """A URL whose response arrived, with the URLs discovered from it."""

    url_id: int
    status_code: int
    # The Content-Type header as received; NULL without one.
    content_type: str | None
    fetched_at: datetime
    response_time_ms: int
    parsed: bool
    parse_error: ParseError | None = None
    parse_error_message: str | None = None
    # NULL when robots.txt was not checked (design D6).
    blocked_by_robots_txt: bool | None = None
    discovered: tuple[NewUrl, ...] = ()
    # What the handlers returned, written in the same unit (design D9).
    rows: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SkippedUrl:
    """A URL recorded without a request, with what the handlers returned for it."""

    url_id: int
    skip_reason: SkipReason
    # The depth the skip was decided on: a URL lowered since then is decided again (design D5).
    crawl_depth: int
    blocked_by_robots_txt: bool | None = None
    rows: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ErroredUrl:
    """A URL whose request got no HTTP response, with what the handlers returned for it."""

    url_id: int
    fetch_error: FetchError
    fetch_error_message: str
    # None without a request of its own: its origin's robots.txt got no response.
    fetched_at: datetime | None
    blocked_by_robots_txt: bool | None = None
    rows: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class RobotsTxtRecord:
    """What an origin's robots.txt request gave, for the origin's row (design D6)."""

    origin: str
    state: RobotsState
    status_code: int | None
    fetch_error: FetchError | None = None
    fetch_error_message: str | None = None
    fetched_at: datetime
    text: str | None
    crawl_delay_ms: int | None
    sitemaps: tuple[str, ...]
