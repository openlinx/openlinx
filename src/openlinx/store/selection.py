"""Resolve the crawl option to a crawl file in the Workspace."""

import os
from pathlib import Path
from stat import S_ISREG
from typing import Any

from sqlalchemy.exc import DBAPIError, MultipleResultsFound, NoResultFound

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import (
    CRAWL_NOT_FOUND,
    CRAWL_NOT_WRITABLE,
    INVALID_VALUE,
    NO_CRAWLS,
)
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.identity import check_crawl_id, identify_file
from openlinx.store.ids import CRAWL_FILE_SUFFIX, crawl_path, is_crawl_id, start_second
from openlinx.store.reading import invalid_crawl_file, read_metadata
from openlinx.store.records import LATEST, CrawlFile
from openlinx.workspace.discovery import Workspace


def resolve_crawl(reference: str, *, workspace: Workspace, cwd: Path) -> CrawlFile:
    if _is_path(reference):
        path = cwd / reference
        # Checked first: a read-only open of a missing file fails like a broken one.
        if not _is_crawl_file(path):
            raise OpenLinxError(
                CRAWL_NOT_FOUND,
                f"No crawl file exists at {path}.",
                hint=f"Check the path, or leave out --crawl to read the {LATEST} Crawl.",
                details={"file": str(path)},
            )
        # Copied and renamed files are allowed: the row, not the name, says which Crawl it is.
        return _selected(path)[0]
    if reference == LATEST:
        crawl_id = _latest(workspace)
    elif is_crawl_id(reference):
        crawl_id = reference
    else:
        raise OpenLinxError(
            INVALID_VALUE,
            f"--crawl {reference} is not {LATEST}, a crawl id or the path of a crawl file.",
            hint=f"Give {LATEST}, an id such as 20260927-140312-k3f9, "
            f"or a path ending in {CRAWL_FILE_SUFFIX}.",
        )
    path = crawl_path(workspace.crawls_dir, crawl_id)
    if not _is_crawl_file(path):
        raise OpenLinxError(
            CRAWL_NOT_FOUND,
            f"No Crawl in the Workspace {workspace.root} has the id {crawl_id}.",
            hint=f"Leave out --crawl to read the {LATEST} Crawl, or give the path of a crawl file.",
        )
    return _selected(path, crawl_id)[0]


def _is_path(reference: str) -> bool:
    # os.altsep is None off Windows; a comprehension keeps the set typed str everywhere.
    separators = {s for s in ("/", os.sep, os.altsep) if s}
    return reference.endswith(CRAWL_FILE_SUFFIX) or any(s in reference for s in separators)


def _selected(path: Path, crawl_id: str | None = None) -> tuple[CrawlFile, dict[str, Any]]:
    """Read the Crawl's metadata through the same resolved identity the writer will verify."""
    try:
        identity = identify_file(path)
        metadata = read_metadata(path, identity=identity)
    except OpenLinxError as error:
        # Keep the reader's schema and busy diagnostics. Only identity loss is stage-specific.
        if error.code != CRAWL_NOT_WRITABLE.code:
            raise
        raise invalid_crawl_file(path) from error
    except (OSError, DBAPIError, NoResultFound, MultipleResultsFound) as error:
        raise invalid_crawl_file(path) from error
    found_id: str = metadata["id"]
    if crawl_id is not None:
        check_crawl_id(path, crawl_id, found_id)
    return CrawlFile(found_id, path, identity=identity), metadata


def _is_crawl_file(path: Path) -> bool:
    # Path.is_file can hide permission errors and make an unreadable file look missing.
    try:
        return S_ISREG(path.stat().st_mode)
    except (FileNotFoundError, NotADirectoryError, ValueError):
        return False
    except OSError as error:
        raise invalid_crawl_file(path) from error


def _latest(workspace: Workspace) -> str:
    crawls_dir = workspace.crawls_dir
    ids = [file.stem for file in crawls_dir.glob(f"*{CRAWL_FILE_SUFFIX}") if is_crawl_id(file.stem)]
    if not ids:
        raise OpenLinxError(
            NO_CRAWLS,
            f"The Workspace {workspace.root} has no Crawl.",
            hint=f"Start one with: {COMMAND_NAME} crawl <url>",
        )
    # The id starts with the start second, so only ids of the newest second can be latest.
    newest_second = start_second(max(ids))
    candidates = [crawl_id for crawl_id in ids if start_second(crawl_id) == newest_second]
    if len(candidates) == 1:
        return candidates[0]
    return max(
        candidates,
        key=lambda crawl_id: (
            _selected(crawl_path(crawls_dir, crawl_id), crawl_id)[1]["started_at"],
            crawl_id,
        ),
    )
