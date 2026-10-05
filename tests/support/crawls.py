"""Creating and reading Crawls in tests (015-add-crawl-store)."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from spider.store.records import NewCrawl
from spider.workspace.discovery import Workspace


def new_crawl(workspace: Workspace) -> NewCrawl:
    """Any Spider-mode Crawl, for tests whose scenario does not name its metadata."""
    return NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        seeds=["https://example.com/"],
        command_argv=["spider", "crawl", "https://example.com/"],
        cwd=workspace.root,
        config={},
    )


def query(file: Path, sql: str) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        return connection.execute(sql).fetchall()


def crawl_row(file: Path) -> dict[str, Any]:
    """The `crawl` row as SQLite stores it, read through a read-only connection."""
    with closing(sqlite3.connect(f"{file.as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        return dict(connection.execute("SELECT * FROM crawl").fetchone())
