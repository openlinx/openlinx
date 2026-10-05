"""What creating a Crawl takes and gives, without loading the store (designs D6 and D9 of 015)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from spider.workspace.discovery import Workspace

type CrawlMode = Literal["spider", "list", "sitemap"]


@dataclass(frozen=True)
class NewCrawl:
    workspace: Workspace
    crawl_mode: CrawlMode
    seeds: Sequence[str]
    command_argv: Sequence[str]
    cwd: Path
    config: Mapping[str, Any]
    section_crawl: bool = False


@dataclass(frozen=True)
class CrawlFile:
    id: str
    path: Path
