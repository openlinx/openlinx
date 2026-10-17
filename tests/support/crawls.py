"""Creating and reading Crawls in tests (015-add-crawl-store)."""

import hashlib
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, delete, insert

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.store.connections import connect
from spider.store.records import CrawlFile, NewCrawl, SecretNames
from spider.store.schema import seeds
from spider.store.writer import CrawlWriter
from spider.workspace.discovery import Workspace, resolve_workspace
from tests.support.clock import FakeClock
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing

# The start time of the spec's example Crawl 20260927-140312-k3f9.
STARTED_AT = datetime(2026, 9, 27, 14, 3, 12, 345000, tzinfo=UTC)


def current_workspace(temp_workspace: TempWorkspace) -> Workspace:
    return resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)


def new_crawl(workspace: Workspace) -> NewCrawl:
    """Any Spider-mode Crawl, for tests whose scenario does not name its metadata."""
    return NewCrawl(
        workspace=workspace,
        crawl_mode="spider",
        seeds=["https://example.com/"],
        command_argv=["spider", "crawl", "https://example.com/"],
        cwd=workspace.root,
        config={},
        scope={
            "mode": "host",
            "hosts": ["example.com"],
            "folder": None,
            "include": [],
            "exclude": [],
        },
        secret_names=SecretNames(),
        journal_setting="auto",
        section_crawl=False,
    )


def create_any_crawl(temp_workspace: TempWorkspace, **changes: Any) -> CrawlFile:
    """`new_crawl` with `changes`, created at `STARTED_AT` where the current folder resolves."""
    request = replace(new_crawl(current_workspace(temp_workspace)), **changes)
    return create_crawl(request, FakeClock(start=STARTED_AT), Collected())


def insert_seed(position: int, url: str) -> Callable[[Connection], None]:
    """A unit that inserts one Seed."""

    def unit(connection: Connection) -> None:
        connection.execute(insert(seeds).values(position=position, url=url))

    return unit


def sha256_of(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def crawl_without_seeds(temp_workspace: TempWorkspace) -> CrawlFile:
    """A Crawl whose seeds table each scenario fills itself."""
    crawl = create_any_crawl(temp_workspace)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(executing(delete(seeds)))
    return crawl


def create_crawl_at(temp_workspace: TempWorkspace, started_at: str, suffix: str) -> CrawlFile:
    """Any Crawl started at the ISO time `started_at`, whose id ends with `suffix`."""
    clock = FakeClock(start=datetime.fromisoformat(started_at))
    return create_crawl(
        new_crawl(current_workspace(temp_workspace)), clock, Collected(), scripted_choice(suffix)
    )


def query(file: Path, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
    with closing(connect(file, read_only=True)) as connection:
        return connection.execute(sql, params).fetchall()


def crawl_row(file: Path) -> dict[str, Any]:
    """The `crawl` row as SQLite stores it, read through a read-only connection."""
    with closing(connect(file, read_only=True)) as connection:
        connection.row_factory = sqlite3.Row
        return dict(connection.execute("SELECT * FROM crawl").fetchone())
