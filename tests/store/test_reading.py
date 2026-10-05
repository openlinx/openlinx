"""Reading a Crawl (015-add-crawl-store, crawl-store)."""

import hashlib
import shutil
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from spider.output.reporter import Collected
from spider.services.crawls import create_crawl
from spider.store.crawls import set_state
from spider.store.reading import read_metadata, reading
from spider.store.records import CrawlFile
from spider.store.schema import seeds
from spider.store.writer import CrawlWriter
from spider.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, create_any_crawl, new_crawl
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace


def test_a_copied_file_opens_by_its_path(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    crawl = create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    )
    copy = temp_workspace.root / "copy" / "c.sqlite"
    copy.parent.mkdir()
    shutil.copyfile(crawl.path, copy)

    assert read_metadata(copy)["id"] == "20260927-140312-k3f9"


def test_a_reader_waits_5_seconds_for_a_lock_and_checks_references(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)

    with reading(crawl.path) as connection:
        pragmas: tuple[int, int] = (
            connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
            connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
        )

    assert pragmas == (1, 5_000)


def completed_crawl(temp_workspace: TempWorkspace) -> CrawlFile:
    crawl = create_any_crawl(temp_workspace)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(lambda connection: set_state(connection, "completed", STARTED_AT))
    return crawl


def test_bytes_are_unchanged_by_reading(temp_workspace: TempWorkspace) -> None:
    crawl = completed_crawl(temp_workspace)
    before = hashlib.sha256(crawl.path.read_bytes()).hexdigest()

    read_metadata(crawl.path)
    with reading(crawl.path) as connection:
        connection.execute(select(seeds)).all()

    assert hashlib.sha256(crawl.path.read_bytes()).hexdigest() == before


def test_writes_through_a_reader_fail(temp_workspace: TempWorkspace) -> None:
    crawl = completed_crawl(temp_workspace)

    with reading(crawl.path) as connection, pytest.raises(DBAPIError) as raised:
        connection.exec_driver_sql(
            "INSERT INTO seeds (position, url) VALUES (9, 'https://example.com/x')"
        )

    assert raised.value.orig.sqlite_errorcode & 0xFF == sqlite3.SQLITE_READONLY  # type: ignore[union-attr]
