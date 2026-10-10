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
    settings_file: Path | None = None
    section_crawl: bool = False
    journal_setting: JournalSetting = "auto"


@dataclass(frozen=True)
class CrawlFile:
    id: str
    path: Path
