"""Resolving --crawl to a crawl file (design D8 of 015-add-crawl-store)."""

import os
from pathlib import Path
from typing import Any

from sqlalchemy.exc import DBAPIError, MultipleResultsFound, NoResultFound

from spider.naming import APP_NAME
from spider.output.codes import CRAWL_FILE_INVALID, CRAWL_NOT_FOUND, INVALID_VALUE, NO_CRAWLS
from spider.output.diagnostics import SpiderError
from spider.store.ids import CRAWL_FILE_SUFFIX, crawl_path, is_crawl_id, start_second
from spider.store.reading import read_metadata
from spider.store.records import LATEST, CrawlFile
from spider.workspace.discovery import Workspace


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    if _is_path(reference):
        path = cwd / reference
        # Checked first: a read-only open of a missing file fails like a broken one.
        if not path.is_file():
            raise SpiderError(
                CRAWL_NOT_FOUND,
                f"No crawl file exists at {path}.",
                hint=f"Check the path, or leave out --crawl to read the {LATEST} Crawl.",
                details={"file": str(path)},
            )
        return _open(path)
    if reference == LATEST:
        crawl_id = _latest(workspace)
    elif is_crawl_id(reference):
        crawl_id = reference
    else:
        raise SpiderError(
            INVALID_VALUE,
            f"--crawl {reference} is not {LATEST}, a crawl id or the path of a crawl file.",
            hint=f"Give {LATEST}, an id such as 20260927-140312-k3f9, "
            f"or a path ending in {CRAWL_FILE_SUFFIX}.",
        )
    path = crawl_path(workspace.crawls_dir, crawl_id)
    if not path.is_file():
        raise SpiderError(
            CRAWL_NOT_FOUND,
            f"No Crawl in the Workspace {workspace.root} has the id {crawl_id}.",
            hint=f"Leave out --crawl to read the {LATEST} Crawl, or give the path of a crawl file.",
        )
    return _open(path)


def _is_path(reference: str) -> bool:
    separators = {"/", os.sep, os.altsep} - {None}
    return reference.endswith(CRAWL_FILE_SUFFIX) or any(s in reference for s in separators)


def _open(path: Path) -> CrawlFile:
    return CrawlFile(_metadata(path)["id"], path)


def _metadata(path: Path) -> dict[str, Any]:
    try:
        return read_metadata(path)
    # Not a SQLite file, no crawl table, or not exactly one crawl row (design D5).
    except (DBAPIError, NoResultFound, MultipleResultsFound) as error:
        raise SpiderError(
            CRAWL_FILE_INVALID,
            f"{path} is not a readable crawl file.",
            hint=f"Give another crawl file, or crawl again with: {APP_NAME} crawl <url>",
            details={"file": str(path)},
        ) from error


def _latest(workspace: Workspace) -> str:
    crawls_dir = workspace.crawls_dir
    ids = [file.stem for file in crawls_dir.glob(f"*{CRAWL_FILE_SUFFIX}") if is_crawl_id(file.stem)]
    if not ids:
        raise SpiderError(
            NO_CRAWLS,
            f"The Workspace {workspace.root} has no Crawl.",
            hint=f"Start one with: {APP_NAME} crawl <url>",
        )
    # The id starts with the start second, so only ids of the newest second can be latest.
    newest_second = start_second(max(ids))
    candidates = [crawl_id for crawl_id in ids if start_second(crawl_id) == newest_second]
    if len(candidates) == 1:
        return candidates[0]
    return max(
        candidates,
        key=lambda crawl_id: (_metadata(crawl_path(crawls_dir, crawl_id))["started_at"], crawl_id),
    )
