"""Verify Crawl file access and SQLite connection settings through the store API."""

import sqlite3
from contextlib import closing

import pytest
from sqlalchemy import Connection

from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.reading import reading
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_without_seeds, create_any_crawl, sha256_of
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace

SETTINGS = ("temp_store", "cache_size", "mmap_size")


def test_a_read_only_crawl_file(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    before = sha256_of(crawl.path)

    with read_only_file(crawl.path), pytest.raises(OpenLinxError) as raised:
        CrawlWriter(crawl.path, FakeClock())

    assert (
        raised.value.code,
        raised.value.diagnostic.details["file"],
        sha256_of(crawl.path),
    ) == ("crawl_not_writable", str(crawl.path), before)


def test_the_writer_waits_30_seconds_for_a_lock_and_checks_references(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        pragmas: tuple[int, int] = writer.run(
            lambda connection: (
                connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
                connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
            )
        )

    assert pragmas == (1, 30_000)


def journal_mode(connection: Connection) -> str:
    return connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()


def connection_settings(connection: Connection) -> tuple[int, ...]:
    return tuple(connection.exec_driver_sql(f"PRAGMA {name}").scalar_one() for name in SETTINGS)


def test_the_writer_s_connection_settings_in_wal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        journal = writer.run(journal_mode)
        settings = writer.run(connection_settings)

    assert (journal, settings) == ("wal", (2, -65536, 268435456))


def test_a_reader_keeps_sqlite_s_defaults(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with reading(crawl.path) as connection:
        settings = connection_settings(connection)
    with closing(sqlite3.connect(crawl.path)) as plain:
        defaults = tuple(plain.execute(f"PRAGMA {name}").fetchone()[0] for name in SETTINGS)

    assert settings == defaults


def test_the_writer_s_connection_settings_in_rollback_journal_mode(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting="delete")

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        journal = writer.run(journal_mode)
        settings = writer.run(connection_settings)

    assert (journal, settings) == ("delete", (2, -65536, 0))
