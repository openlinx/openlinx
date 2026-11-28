"""Read Crawl files through a read-only engine scoped to each operation."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, select
from sqlalchemy.exc import DBAPIError

from openlinx.naming import COMMAND_NAME, PRODUCT_NAME
from openlinx.output.codes import CRAWL_FILE_INVALID, CRAWL_SCHEMA_TOO_NEW
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.connections import READER_BUSY_SECONDS, busy_error, is_busy, opening
from openlinx.store.identity import check_crawl_id
from openlinx.store.preview import HEALTH_COLUMNS, is_historical_preview, missing_health_columns
from openlinx.store.records import CrawlFile, CrawlFileIdentity
from openlinx.store.schema import SCHEMA_VERSION, crawl

_CRAWL_ID = select(crawl.c.id)
_CRAWL_METADATA = select(crawl)
_PREVIEW_METADATA = select(*(column for column in crawl.c if column.name not in HEALTH_COLUMNS))


@contextmanager
def reading(
    path: Path,
    *,
    identity: CrawlFileIdentity | None = None,
    snapshot: bool = False,
    busy_seconds: float = READER_BUSY_SECONDS,
) -> Iterator[Connection]:
    """Pin a snapshot in WAL and on request in rollback-journal mode."""
    try:
        with (
            opening(path, role="read", identity=identity, busy_seconds=busy_seconds) as engine,
            engine.connect() as connection,
        ):
            # Legacy SQLite transactions do not begin on SELECT. A rollback-journal
            # snapshot can delay Writer commits, so compound readers opt in.
            if snapshot or connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal":
                connection.exec_driver_sql("BEGIN")
            _check_schema_version(connection, path)
            yield connection
    except DBAPIError as error:
        if not is_busy(error):
            raise
        raise busy_error(path, "reading", busy_seconds, error) from error


@contextmanager
def reading_selected(
    selected: CrawlFile, *, busy_seconds: float = READER_BUSY_SECONDS
) -> Iterator[Connection]:
    """Confirm the recorded Crawl ID in the snapshot used for the response."""
    with reading(
        selected.path, identity=selected.identity, snapshot=True, busy_seconds=busy_seconds
    ) as connection:
        check_crawl_id(selected.path, selected.id, connection.execute(_CRAWL_ID).scalar_one())
        yield connection


def _check_schema_version(connection: Connection, path: Path) -> None:
    # Read before any declared table: a newer file may have changed them.
    version: int = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
    if version > SCHEMA_VERSION:
        raise OpenLinxError(
            CRAWL_SCHEMA_TOO_NEW,
            f"The crawl file {path} has schema version {version}, newer than this tool's "
            f"{SCHEMA_VERSION}.",
            hint=f"Upgrade {PRODUCT_NAME} to read it.",
            details={"file_schema_version": version, "tool_schema_version": SCHEMA_VERSION},
        )


def read_metadata(path: Path, *, identity: CrawlFileIdentity | None = None) -> dict[str, Any]:
    with reading(path, identity=identity, snapshot=True) as connection:
        statement = _CRAWL_METADATA
        if is_historical_preview(connection, missing_health_columns(connection)):
            statement = _PREVIEW_METADATA
        return dict(connection.execute(statement).mappings().one())


def invalid_crawl_file(path: Path) -> OpenLinxError:
    return OpenLinxError(
        CRAWL_FILE_INVALID,
        f"{path} is not a readable crawl file.",
        hint=f"Give another crawl file, or crawl again with: {COMMAND_NAME} crawl <url>",
        details={"file": str(path)},
    )
