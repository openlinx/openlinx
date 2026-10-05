"""Crawl files in the Workspace's data folder (designs D1 and D2 of 015-add-crawl-store)."""

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
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
    # Read once: the id and the Crawl's recorded start time must name the same instant.
    started_at = clock.now()
    crawl_file = _claim_new_file(workspace, started_at, choice)
    try:
        _write_new_file(crawl_file)
    except BaseException:
        # A claimed file left empty would break --crawl latest in this Workspace.
        crawl_file.path.unlink()
        raise
    return crawl_file


def _claim_new_file(workspace: Workspace, started_at: datetime, choice: Choice) -> CrawlFile:
    while True:
        crawl_id = new_crawl_id(started_at, choice)
        path = workspace.crawls_dir / f"{crawl_id}.sqlite"
        # Exclusive create: of two processes that draw the same id, only one gets the file.
        try:
            path.open("xb").close()
        except FileExistsError:
            continue
        return CrawlFile(crawl_id, path)


def _write_new_file(crawl_file: CrawlFile) -> None:
    engine = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(crawl_file.path), poolclass=NullPool
    )
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(insert(crawl).values(id=crawl_file.id))
    finally:
        engine.dispose()
