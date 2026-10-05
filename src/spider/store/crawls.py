"""Crawl files in the Workspace's data folder (designs D1 and D2 of 015-add-crawl-store)."""

import sqlite3
from datetime import datetime

from sqlalchemy import create_engine, insert
from sqlalchemy.pool import NullPool

from spider import __version__
from spider.store.ids import Choice, new_crawl_id
from spider.store.records import CrawlFile, NewCrawl
from spider.store.schema import SCHEMA_VERSION, crawl, metadata, seeds
from spider.workspace.creation import create_data_folder


def create_crawl_file(request: NewCrawl, started_at: datetime, choice: Choice) -> CrawlFile:
    create_data_folder(request.workspace)
    crawl_file = _claim_new_file(request, started_at, choice)
    try:
        _write_new_file(crawl_file, request, started_at)
    except BaseException:
        # A claimed file left empty would break --crawl latest in this Workspace.
        crawl_file.path.unlink()
        raise
    return crawl_file


def _claim_new_file(request: NewCrawl, started_at: datetime, choice: Choice) -> CrawlFile:
    while True:
        crawl_id = new_crawl_id(started_at, choice)
        path = request.workspace.crawls_dir / f"{crawl_id}.sqlite"
        # Exclusive create: of two processes that draw the same id, only one gets the file.
        try:
            path.open("xb").close()
        except FileExistsError:
            continue
        return CrawlFile(crawl_id, path)


def _write_new_file(crawl_file: CrawlFile, request: NewCrawl, started_at: datetime) -> None:
    settings_file = request.workspace.settings_file
    engine = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(crawl_file.path), poolclass=NullPool
    )
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute(
                insert(crawl).values(
                    id=crawl_file.id,
                    crawl_mode=request.crawl_mode,
                    section_crawl=request.section_crawl,
                    state="running",
                    started_at=started_at,
                    command_argv=list(request.command_argv),
                    cwd=str(request.cwd),
                    settings_file=str(settings_file) if settings_file.is_file() else None,
                    config=dict(request.config),
                    tool_version=__version__,
                    schema_version=SCHEMA_VERSION,
                )
            )
            connection.execute(
                insert(seeds),
                [
                    {"position": position, "url": url}
                    for position, url in enumerate(request.seeds, start=1)
                ],
            )
    finally:
        engine.dispose()
