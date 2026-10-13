"""The store's records and enumerations, loading no sqlalchemy (designs D6 and D9 of 015)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from spider.crawl.urls import NormalizedUrl
from spider.workspace.discovery import Workspace

type CrawlMode = Literal["spider", "list", "sitemap"]
type JournalMode = Literal["wal", "delete"]
type JournalSetting = Literal["auto", "wal", "delete"]
type CrawlState = Literal["running", "stopped", "completed", "failed", "interrupted"]
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

# The --crawl value that selects the Crawl that started last.
LATEST = "latest"


@dataclass(frozen=True)
class SecretNames:
    """The secret flags, such as --token, and secret settings, such as example.token."""

    flags: frozenset[str] = frozenset()
    settings: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NewCrawl:
    workspace: Workspace
    crawl_mode: CrawlMode
    seeds: Sequence[str]
    command_argv: Sequence[str]
    cwd: Path
    config: Mapping[str, Any]
    # No defaults: a creator that forgot its secrets would record them, and one that forgot the
    # store.journal_mode setting would silently ignore it.
    secret_names: SecretNames
    journal_setting: JournalSetting
    settings_file: Path | None = None
    section_crawl: bool = False


@dataclass(frozen=True)
class CrawlFile:
    id: str
    path: Path


@dataclass(frozen=True, slots=True)
class QueuedUrl:
    """A URL the frontier hands to the engine."""

    id: int
    url: NormalizedUrl


@dataclass(frozen=True, slots=True, kw_only=True)
class NewUrl:
    """A URL discovered from a response, recorded unless the Crawl has it already."""

    url: NormalizedUrl
    host: str
    crawl_depth: int
    discovered_via: DiscoveredVia


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
    crawl_mode: CrawlMode
    section_crawl: bool
    started_at: str
    seed: str
    seed_count: int
