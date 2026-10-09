"""Crawl files in the Workspace's data folder (designs D1 and D2 of 015-add-crawl-store)."""

import platform
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, insert, update
from sqlalchemy.exc import DBAPIError

from spider import __version__
from spider.output.codes import WORKSPACE_NOT_WRITABLE
from spider.output.diagnostics import SpiderError
from spider.store.connections import connect, not_writable_name, opening
from spider.store.ids import Choice, crawl_path, new_crawl_id
from spider.store.records import CrawlFile, CrawlState, JournalMode, NewCrawl
from spider.store.schema import SCHEMA_VERSION, crawl, metadata, seeds
from spider.workspace.creation import as_workspace_not_writable, create_data_folder


def create_crawl_file(
    request: NewCrawl, started_at: datetime, choice: Choice, journal_mode: JournalMode
) -> CrawlFile:
    workspace = request.workspace
    create_data_folder(workspace)
    # A permissions problem must reach an agent as an error code, never as a traceback.
    with as_workspace_not_writable(workspace):
        crawl_file = _claim_new_file(workspace.crawls_dir, started_at, choice)
        try:
            with _sqlite_not_writable(crawl_file.path):
                _write_new_file(crawl_file, request, started_at, journal_mode)
        except BaseException:
            # A claimed file left empty would break --crawl latest in this Workspace.
            crawl_file.path.unlink()
            raise
    return crawl_file


def set_state(connection: Connection, state: CrawlState, at: datetime) -> None:
    completed_at = at if state == "completed" else None
    connection.execute(update(crawl).values(state=state, completed_at=completed_at))


def _claim_new_file(crawls_dir: Path, started_at: datetime, choice: Choice) -> CrawlFile:
    while True:
        crawl_id = new_crawl_id(started_at, choice)
        path = crawl_path(crawls_dir, crawl_id)
        # Exclusive create: of two processes that draw the same id, only one gets the file.
        try:
            path.open("xb").close()
        except FileExistsError:
            continue
        return CrawlFile(crawl_id, path)


def _write_new_file(
    crawl_file: CrawlFile, request: NewCrawl, started_at: datetime, journal_mode: JournalMode
) -> None:
    # The journal mode belongs to the file, so it is set once, outside any transaction.
    with closing(connect(crawl_file.path)) as connection:
        (granted,) = connection.execute(f"PRAGMA journal_mode = {journal_mode}").fetchone()
    settings_file = request.settings_file
    with opening(crawl_file.path) as engine, engine.begin() as connection:
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
                cwd=str(request.cwd.absolute()),
                settings_file=None if settings_file is None else str(settings_file.absolute()),
                config=dict(request.config),
                tool_version=__version__,
                schema_version=SCHEMA_VERSION,
                journal_mode=granted,
                python_version=platform.python_version(),
                platform=platform.platform(),
            )
        )
        connection.execute(
            insert(seeds),
            [
                {"position": position, "url": url}
                for position, url in enumerate(request.seeds, start=1)
            ],
        )


@contextmanager
def _sqlite_not_writable(file: Path) -> Iterator[None]:
    try:
        yield
    except (sqlite3.Error, DBAPIError) as error:
        name = not_writable_name(error)
        if name is None:
            raise
        raise SpiderError(
            WORKSPACE_NOT_WRITABLE,
            f"Cannot write the new crawl file {file}.",
            details={"path": str(file), "error": name},
        ) from error
