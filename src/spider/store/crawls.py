"""Crawl files in the Workspace's data folder (designs D1 and D2 of 015-add-crawl-store)."""

import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, insert
from sqlalchemy.pool import NullPool

from spider.clock import Clock
from spider.store.ids import Choice, new_crawl_id
from spider.store.schema import crawl, metadata
from spider.workspace.creation import create_data_folder
from spider.workspace.discovery import Workspace


@dataclass(frozen=True)
class CrawlFile:
    id: str
    path: Path


def create_crawl(workspace: Workspace, clock: Clock, choice: Choice = secrets.choice) -> CrawlFile:
    create_data_folder(workspace)
    created = _claim_new_file(workspace, clock, choice)
    engine = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(created.path), poolclass=NullPool
    )
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(insert(crawl).values(id=created.id))
    finally:
        engine.dispose()
    return created


def _claim_new_file(workspace: Workspace, clock: Clock, choice: Choice) -> CrawlFile:
    started_at = clock.now()
    while True:
        crawl_id = new_crawl_id(started_at, choice)
        path = workspace.crawls_dir / f"{crawl_id}.sqlite"
        # Exclusive create: of two processes that draw the same id, only one gets the file.
        try:
            path.open("xb").close()
        except FileExistsError:
            continue
        return CrawlFile(crawl_id, path)
