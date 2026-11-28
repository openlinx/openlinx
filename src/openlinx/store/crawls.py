"""Create Crawl files under the writer claim and update run metadata (060 D12)."""

import os
import platform
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, closing, contextmanager
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson
from sqlalchemy import Connection, func, insert, select, update
from sqlalchemy.exc import DBAPIError

from openlinx import __version__
from openlinx.json_numbers import decode_json_object
from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import CRAWL_FILE_INVALID, WORKSPACE_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.claim import claim_writer
from openlinx.store.connections import connect, not_writable_name, opening
from openlinx.store.identity import check_crawl_id, identify_file
from openlinx.store.ids import Choice, crawl_path, new_crawl_id
from openlinx.store.journal import JournalChoice, confirm_journal_mode
from openlinx.store.preview import is_historical_preview, missing_health_columns
from openlinx.store.reading import reading
from openlinx.store.records import (
    CrawlFile,
    CrawlState,
    CrawlSummary,
    NewCrawl,
    RecordedCrawl,
    RecordedScope,
    StopReason,
)
from openlinx.store.schema import (
    SCHEMA_VERSION,
    affected_urls,
    crawl,
    crawl_runs,
    issues,
    metadata,
    rules,
    seeds,
)
from openlinx.store.transitions import check_transition
from openlinx.store.urls import requeue_for_a_continue
from openlinx.workspace.creation import as_workspace_not_writable, create_data_folder

FIRST_RUN_ID = 1
_FIRST_RUN = insert(crawl_runs).values(id=FIRST_RUN_ID, detached=False)
_CONTINUED_RUN = (
    insert(crawl_runs).values(command_argv=[], detached=False).returning(crawl_runs.c.id)
)

_SUMMARY = select(
    crawl.c.state,
    crawl.c.stop_reason,
    crawl.c.crawl_mode,
    crawl.c.section_crawl,
    crawl.c.started_at,
)
_FIRST_SEED = select(seeds.c.url).order_by(seeds.c.position).limit(1)
_SEED_COUNT = select(func.count()).select_from(seeds)


@contextmanager
def create_crawl_file(
    request: NewCrawl, started_at: datetime, choice: Choice, journal: JournalChoice
) -> Iterator[tuple[CrawlFile, JournalChoice]]:
    workspace = request.workspace
    create_data_folder(workspace)
    with ExitStack() as ownership:
        # Only creation errors belong to the Workspace; the caller runs after this block.
        with as_workspace_not_writable(workspace):
            crawl_file = ownership.enter_context(
                _claim_new_file(workspace.crawls_dir, started_at, choice)
            )
            try:
                crawl_file = replace(crawl_file, identity=identify_file(crawl_file.path))
                with _sqlite_not_writable(crawl_file.path):
                    journal, granted = _set_journal_mode(
                        crawl_file.path, journal, workspace.data_dir
                    )
                    _write_new_file(crawl_file, request, started_at, granted)
            except BaseException:
                # A claimed file left empty would break --crawl latest in this Workspace.
                crawl_file.path.unlink()
                raise
        yield crawl_file, journal


def set_state(
    connection: Connection, state: CrawlState, at: datetime, stop_reason: StopReason | None = None
) -> None:
    """The one writer of how a Crawl ends, checked against its state."""
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


def record_scope(scope: RecordedScope) -> Callable[[Connection], None]:
    """A unit that records the Scope again, once a Seed's Redirect Chain widened it."""
    statement = update(crawl).values(scope=dict(scope))

    def unit(connection: Connection) -> None:
        connection.execute(statement)

    return unit


def read_recorded(path: Path, *, selected: CrawlFile | None = None) -> RecordedCrawl:
    with reading(path, identity=selected.identity if selected is not None else None) as connection:
        row = connection.execute(
            select(
                crawl.c.id,
                crawl.c.state,
                crawl.c.crawl_mode,
                crawl.c.config,
                crawl.c.scope,
                crawl.c.warnings,
            )
        ).one()
        if selected is not None:
            check_crawl_id(selected.path, selected.id, row.id)
        check_rule_schema(connection, path)
        _check_health_columns(connection, path)
        urls: list[str] = list(
            connection.execute(select(seeds.c.url).order_by(seeds.c.position)).scalars()
        )
        return RecordedCrawl(
            state=row.state,
            crawl_mode=row.crawl_mode,
            config=decode_json_object(row.config),
            scope=orjson.loads(row.scope),
            seeds=tuple(urls),
            warnings=tuple(orjson.loads(row.warnings)),
        )


def check_rule_schema(connection: Connection, path: Path) -> None:
    """Refuse Crawl files missing the Rule tables or the stored Issues view."""
    table_names = (rules.name, affected_urls.name)
    present: set[str] = set(
        connection.exec_driver_sql(
            "SELECT name FROM sqlite_schema WHERE (type = 'table' AND name IN (?, ?))"
            " OR (type = 'view' AND name = ?)",
            (*table_names, issues.name),
        ).scalars()
    )
    missing_tables = ", ".join(name for name in table_names if name not in present)
    missing = []
    if missing_tables:
        missing.append(f"required Rule tables: {missing_tables}")
    if issues.name not in present:
        missing.append(f"required Rule view: {issues.name}")
    if missing:
        objects = " and ".join(missing)
        raise OpenLinxError(
            CRAWL_FILE_INVALID,
            f"The crawl file {path} is missing {objects}.",
            hint="Crawl again with this tool to record Rules and their Affected URLs.",
            details={"file": str(path)},
        )


def _check_health_columns(connection: Connection, path: Path) -> None:
    """Refuse unsupported layouts before Continue reaches the Writer or Fetcher."""
    missing = missing_health_columns(connection)
    if missing and not is_historical_preview(connection, missing):
        raise OpenLinxError(
            CRAWL_FILE_INVALID,
            f"The crawl file {path} is missing required Health columns {', '.join(missing)}.",
            hint="Crawl again with this tool to record the Health Score.",
            details={"file": str(path)},
        )


def record_continue(
    config: Mapping[str, Any], at: datetime, *, run_pid: int | None = None
) -> Callable[[Connection], int | None]:
    """Restore the Crawl to running, persist its settings and requeue transient outcomes.

    With an owning PID, record a run in the same transaction and return its id. The
    internal Continue Service has no command line to record.
    """

    def unit(connection: Connection) -> int | None:
        set_state(connection, "running", at)
        connection.execute(update(crawl).values(config=dict(config)))
        requeue_for_a_continue(connection)
        if run_pid is None:
            return None
        # The owner holds the claim, so replay will allocate the same id.
        run_id: int = connection.execute(
            _CONTINUED_RUN, {"started_at": at, "pid": run_pid}
        ).scalar_one()
        return run_id

    return unit


def record_warnings(warnings: Sequence[Mapping[str, Any]]) -> Callable[[Connection], None]:
    """A unit that writes the Crawl's warnings, as JSON objects."""

    def unit(connection: Connection) -> None:
        connection.execute(update(crawl).values(warnings=list(warnings)))

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


@contextmanager
def _claim_new_file(crawls_dir: Path, started_at: datetime, choice: Choice) -> Iterator[CrawlFile]:
    while True:
        crawl_id = new_crawl_id(started_at, choice)
        path = crawl_path(crawls_dir, crawl_id)
        if path.exists():
            continue
        crawl_file = CrawlFile(crawl_id, path)
        with ExitStack() as ownership:
            # Reserve the claim file atomically: an existence check would race its creator.
            try:
                ownership.enter_context(claim_writer(crawl_file, exclusive=True))
                path.open("xb").close()
            except FileExistsError:
                continue
            yield crawl_file
            return


def _set_journal_mode(
    path: Path, journal: JournalChoice, location: Path
) -> tuple[JournalChoice, str]:
    """The confirmed choice, and the mode SQLite granted."""
    # The journal mode belongs to the file, so it is set once, outside any transaction.
    with closing(connect(path)) as connection:
        (granted,) = connection.execute(f"PRAGMA journal_mode = {journal.mode}").fetchone()
        confirmed = confirm_journal_mode(journal, granted, location)
        if granted != confirmed.mode:
            # SQLite refused WAL; no test can make it refuse.
            (granted,) = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    return confirmed, granted


def _write_new_file(
    crawl_file: CrawlFile, request: NewCrawl, started_at: datetime, journal_mode: str
) -> None:
    settings_file = request.settings_file
    run_argv = [COMMAND_NAME, *request.command_argv[1:]] if request.command_argv else []
    with (
        opening(crawl_file.path, role="create", identity=crawl_file.identity) as engine,
        engine.begin() as connection,
    ):
        metadata.create_all(connection)
        connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute(
            insert(crawl).values(
                id=crawl_file.id,
                crawl_mode=request.crawl_mode,
                section_crawl=request.section_crawl,
                scope=dict(request.scope),
                warnings=[],
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
        connection.execute(
            _FIRST_RUN,
            {
                "started_at": started_at,
                "command_argv": run_argv,
                "pid": os.getpid(),
            },
        )
        if request.rules:
            connection.execute(insert(rules), [asdict(rule) for rule in request.rules])


@contextmanager
def _sqlite_not_writable(file: Path) -> Iterator[None]:
    try:
        yield
    except (sqlite3.Error, DBAPIError) as error:
        name = not_writable_name(error)
        if name is None:
            raise
        raise OpenLinxError(
            WORKSPACE_NOT_WRITABLE,
            f"Cannot write the new crawl file {file}.",
            details={"path": str(file), "error": name},
        ) from error
