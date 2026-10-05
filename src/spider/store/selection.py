"""Resolving --crawl to a crawl file (design D8 of 015-add-crawl-store)."""

import os
from pathlib import Path
from typing import Any

from sqlalchemy.exc import DBAPIError

from spider.naming import APP_NAME
from spider.output.codes import CRAWL_FILE_INVALID, CRAWL_NOT_FOUND, INVALID_VALUE, NO_CRAWLS
from spider.output.diagnostics import SpiderError
from spider.store.ids import is_crawl_id
from spider.store.reading import read_metadata
from spider.store.records import LATEST, CrawlFile
from spider.workspace.discovery import Workspace


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    if _is_path(reference):
        path = cwd / reference
        return _open(path)
    if reference == LATEST:
        reference = _latest(workspace)
    elif not is_crawl_id(reference):
        raise SpiderError(
            INVALID_VALUE,
            f"--crawl {reference} is not latest, a crawl id or the path of a crawl file.",
            hint="Give latest, an id such as 20260927-140312-k3f9, or a path ending in .sqlite.",
        )
    path = workspace.crawls_dir / f"{reference}.sqlite"
    if not path.is_file():
        raise SpiderError(
            CRAWL_NOT_FOUND,
            f"No Crawl in the Workspace {workspace.root} has the id {reference}.",
            hint="Leave out --crawl to read the latest Crawl, or give the path of a crawl file.",
        )
    return _open(path)


def _is_path(reference: str) -> bool:
    separators = {"/", os.sep, os.altsep} - {None}
    return reference.endswith(".sqlite") or any(s in reference for s in separators)


def _open(path: Path) -> CrawlFile:
    return CrawlFile(_metadata(path)["id"], path)


def _metadata(path: Path) -> dict[str, Any]:
    try:
        return read_metadata(path)
    except DBAPIError as error:
        raise SpiderError(
            CRAWL_FILE_INVALID,
            f"{path} is not a readable crawl file.",
            hint=f"Give another crawl file, or crawl again with: {APP_NAME} crawl <url>",
            details={"file": str(path)},
        ) from error


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
            _metadata(crawls_dir / f"{crawl_id}.sqlite")["started_at"],
            crawl_id,
        ),
    )


def _second(crawl_id: str) -> str:
    return crawl_id.rsplit("-", 1)[0]
