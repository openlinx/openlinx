"""Resolving --crawl to a crawl file (design D8 of 015-add-crawl-store)."""

from pathlib import Path

from spider.store.records import CrawlFile
from spider.workspace.discovery import Workspace


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    return CrawlFile(reference, workspace.crawls_dir / f"{reference}.sqlite")
