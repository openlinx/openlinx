"""The store's records and enumerations, loading no sqlalchemy (designs D6 and D9 of 015)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
