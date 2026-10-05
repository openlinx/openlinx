"""Resolving --crawl to a crawl file (design D8 of 015-add-crawl-store)."""

from pathlib import Path

from spider.naming import APP_NAME
from spider.output.codes import CRAWL_NOT_FOUND, NO_CRAWLS
from spider.output.diagnostics import SpiderError
from spider.store.ids import is_crawl_id
from spider.store.reading import read_metadata
from spider.store.records import CrawlFile
from spider.workspace.discovery import Workspace

LATEST = "latest"


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    if reference == LATEST:
        reference = _latest(workspace)
    path = workspace.crawls_dir / f"{reference}.sqlite"
    if not path.is_file():
        raise SpiderError(
            CRAWL_NOT_FOUND,
            f"No Crawl in the Workspace {workspace.root} has the id {reference}.",
            hint="Leave out --crawl to read the latest Crawl, or give the path of a crawl file.",
        )
    return CrawlFile(reference, path)


def _latest(workspace: Workspace) -> str:
    crawls_dir = workspace.crawls_dir
    ids = [file.stem for file in crawls_dir.glob("*.sqlite") if is_crawl_id(file.stem)]
    if not ids:
        raise SpiderError(
            NO_CRAWLS,
            f"The Workspace {workspace.root} has no Crawl.",
            hint=f"Start one with: {APP_NAME} crawl <url>",
        )
    # The id starts with the start second, so only ids of the newest second can be latest.
    newest_second = _second(max(ids))
    candidates = [crawl_id for crawl_id in ids if _second(crawl_id) == newest_second]
    if len(candidates) == 1:
        return candidates[0]
    return max(
        candidates,
        key=lambda crawl_id: (
            read_metadata(crawls_dir / f"{crawl_id}.sqlite")["started_at"],
            crawl_id,
        ),
    )


def _second(crawl_id: str) -> str:
    return crawl_id.rsplit("-", 1)[0]
