"""Resolving --crawl to a crawl file (design D8 of 015-add-crawl-store)."""

from pathlib import Path

from spider.store.records import CrawlFile
from spider.workspace.discovery import Workspace

LATEST = "latest"


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    if reference == LATEST:
        # The id starts with the start time, so the greatest id started last.
        reference = max(file.stem for file in workspace.crawls_dir.glob("*.sqlite"))
    return CrawlFile(reference, workspace.crawls_dir / f"{reference}.sqlite")
