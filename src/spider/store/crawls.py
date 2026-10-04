"""Crawl files in the Workspace's data folder (design D2 of 015-add-crawl-store)."""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, insert
from sqlalchemy.pool import NullPool

from spider.store.schema import crawl, metadata
from spider.workspace.creation import create_data_folder
from spider.workspace.discovery import Workspace


def create_crawl(workspace: Workspace, *, crawl_id: str) -> Path:
    create_data_folder(workspace)
    file = workspace.crawls_dir / f"{crawl_id}.sqlite"
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(file), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(insert(crawl).values(id=crawl_id))
    finally:
        engine.dispose()
    return file
