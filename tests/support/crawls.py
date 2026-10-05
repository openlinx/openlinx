"""Creating and reading Crawls in tests (015-add-crawl-store)."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.store.connections import connect, opening
from spider.store.records import CrawlFile, NewCrawl
from spider.workspace.discovery import Workspace, resolve_workspace
from tests.support.clock import FakeClock
from tests.support.workspace import TempWorkspace

# The start time of the spec's example Crawl 20260927-140312-k3f9.
STARTED_AT = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)


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


def create_any_crawl(temp_workspace: TempWorkspace, **changes: Any) -> CrawlFile:
    """`new_crawl` with `changes`, created at `STARTED_AT` where the current folder resolves."""
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    request = replace(new_crawl(workspace), **changes)
    return create_crawl(request, FakeClock(start=STARTED_AT), Collected())


def query(file: Path, sql: str) -> list[tuple[Any, ...]]:
    with closing(connect(file, read_only=True)) as connection:
        return connection.execute(sql).fetchall()


def crawl_row(file: Path) -> dict[str, Any]:
    """The `crawl` row as SQLite stores it, read through a read-only connection."""
    with closing(connect(file, read_only=True)) as connection:
        connection.row_factory = sqlite3.Row
        return dict(connection.execute("SELECT * FROM crawl").fetchone())


def run_unit[T](file: Path, unit: Callable[[Connection], T]) -> T:
    """Until the writer of group 4 runs units: one unit, in its own committed transaction."""
    with opening(file) as engine, engine.begin() as connection:
        return unit(connection)
