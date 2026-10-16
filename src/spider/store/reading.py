"""Reading crawl files read-only, one engine per operation (design D2 of 015-add-crawl-store)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Row, select
from sqlalchemy.exc import DBAPIError

from spider.naming import APP_NAME
from spider.output.codes import CRAWL_SCHEMA_TOO_NEW
from spider.output.diagnostics import SpiderError
from spider.store.connections import READER_BUSY_SECONDS, busy_error, is_busy, opening
from spider.store.schema import SCHEMA_VERSION, crawl


@contextmanager
def reading(path: Path) -> Iterator[Connection]:
    try:
        with opening(path, role="read") as engine, engine.connect() as connection:
            # One snapshot for the whole read, in WAL mode, where it costs the writer nothing:
            # pysqlite begins no transaction before a SELECT, so each statement would see the
            # file as it is then. In rollback-journal mode the read's SHARED lock would hold
            # the writer's commit for the whole read, so there each statement reads alone.
            journal_mode: str = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
            if journal_mode == "wal":
                connection.exec_driver_sql("BEGIN")
            _check_schema_version(connection, path)
            yield connection
    except DBAPIError as error:
        if not is_busy(error):
            raise
        raise busy_error(path, "reading", READER_BUSY_SECONDS, error) from error


def _check_schema_version(connection: Connection, path: Path) -> None:
    # Read before any declared table: a newer file may have changed them (design D5).
    version: int = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
    if version > SCHEMA_VERSION:
        raise SpiderError(
            CRAWL_SCHEMA_TOO_NEW,
            f"The crawl file {path} has schema version {version}, newer than this tool's "
            f"{SCHEMA_VERSION}.",
            hint=f"Upgrade {APP_NAME} to read it.",
            details={"file_schema_version": version, "tool_schema_version": SCHEMA_VERSION},
        )


def row_dict(row: Row[Any]) -> dict[str, Any]:
    # A column's name is sqlalchemy's quoted_name, a str subclass that orjson refuses as
    # a key and that equals the str it names, so only the exact type shows it.
    return {str(name): value for name, value in row._mapping.items()}


def read_metadata(path: Path) -> dict[str, Any]:
    with reading(path) as connection:
        return row_dict(connection.execute(select(crawl)).one())
