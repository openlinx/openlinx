"""Crawl files in the Workspace's data folder (designs D1 and D2 of 015-add-crawl-store)."""

import platform
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.exc import DBAPIError

from spider import __version__
from spider.output.codes import WORKSPACE_NOT_WRITABLE
from spider.output.diagnostics import SpiderError
from spider.store.connections import connect, not_writable_name, opening
from spider.store.ids import Choice, crawl_path, new_crawl_id
from spider.store.journal import JournalChoice, confirm_journal_mode
from spider.store.records import CrawlFile, CrawlState, CrawlSummary, NewCrawl, StopReason
from spider.store.schema import SCHEMA_VERSION, crawl, metadata, seeds
from spider.store.transitions import check_transition
from spider.workspace.creation import as_workspace_not_writable, create_data_folder

_SUMMARY = select(
    crawl.c.state,
    crawl.c.stop_reason,
    crawl.c.crawl_mode,
    crawl.c.section_crawl,
    crawl.c.started_at,
)
_FIRST_SEED = select(seeds.c.url).order_by(seeds.c.position).limit(1)
_SEED_COUNT = select(func.count()).select_from(seeds)


def create_crawl_file(
    request: NewCrawl, started_at: datetime, choice: Choice, journal: JournalChoice
) -> tuple[CrawlFile, JournalChoice]:
    workspace = request.workspace
    create_data_folder(workspace)
    # A permissions problem must reach an agent as an error code, never as a traceback.
    with as_workspace_not_writable(workspace):
        crawl_file = _claim_new_file(workspace.crawls_dir, started_at, choice)
        try:
            with _sqlite_not_writable(crawl_file.path):
                journal, granted = _set_journal_mode(crawl_file.path, journal, workspace.data_dir)
                _write_new_file(crawl_file, request, started_at, granted)
        except BaseException:
            # A claimed file left empty would break --crawl latest in this Workspace.
            crawl_file.path.unlink()
            raise
    return crawl_file, journal


def set_state(
    connection: Connection, state: CrawlState, at: datetime, stop_reason: StopReason | None = None
) -> None:
    """The one writer of how a Crawl ends, checked against the state it reads (020 D12)."""
    current: CrawlState = connection.execute(select(crawl.c.state)).scalar_one()
    check_transition(current, state, stop_reason)
    completed_at = at if state == "completed" else None
    connection.execute(
        update(crawl).values(state=state, completed_at=completed_at, stop_reason=stop_reason)
    )


def record_state(
    state: CrawlState, at: datetime, stop_reason: StopReason | None = None
) -> Callable[[Connection], None]:
    """A unit that writes the Crawl State, as set_state checks it."""

    def unit(connection: Connection) -> None:
        set_state(connection, state, at, stop_reason)

    return unit


def crawl_summary() -> Callable[[Connection], CrawlSummary]:
    """A unit that only reads: the crawl and seeds values of a Crawl's result."""

    def unit(connection: Connection) -> CrawlSummary:
        row = connection.execute(_SUMMARY).one()
        return CrawlSummary(
            state=row.state,
            stop_reason=row.stop_reason,
            crawl_mode=row.crawl_mode,
            section_crawl=bool(row.section_crawl),
            started_at=row.started_at,
            seed=connection.execute(_FIRST_SEED).scalar_one(),
            seed_count=connection.execute(_SEED_COUNT).scalar_one(),
        )

    return unit


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


def _set_journal_mode(
    path: Path, journal: JournalChoice, location: Path
) -> tuple[JournalChoice, str]:
    """The confirmed choice, and the mode SQLite granted."""
    # The journal mode belongs to the file, so it is set once, outside any transaction.
    with closing(connect(path)) as connection:
        (granted,) = connection.execute(f"PRAGMA journal_mode = {journal.mode}").fetchone()
        confirmed = confirm_journal_mode(journal, granted, location)
        if granted != confirmed.mode:
            # SQLite refused WAL; no test can make it refuse (design D3).
            (granted,) = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    return confirmed, granted


def _write_new_file(
    crawl_file: CrawlFile, request: NewCrawl, started_at: datetime, journal_mode: str
) -> None:
    settings_file = request.settings_file
    with opening(crawl_file.path, role="create") as engine, engine.begin() as connection:
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
                journal_mode=journal_mode,
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
