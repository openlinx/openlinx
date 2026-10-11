"""Durability across a killed writer process (015-add-crawl-store, crawl-store)."""

import pytest

from spider.output.diagnostics import SpiderError
from spider.store.selection import resolve_crawl
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import (
    crawl_without_seeds,
    create_any_crawl,
    current_workspace,
    insert_seed,
    query,
)
from tests.support.store_worker import StoreWorker
from tests.support.workspace import TempWorkspace

# Every test here starts a real process.
pytestmark = pytest.mark.slow

COUNT = "SELECT count(*) FROM seeds"
# Long enough for SQLite to retry, short enough to keep the test quick.
SHORT_BUSY_SECONDS = 0.2


def test_a_store_worker_is_the_writer_process_itself(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with StoreWorker(crawl.path) as worker:
        writer = worker.pid

    assert writer == worker.process.pid


def test_a_killed_writer_keeps_committed_units_in_a_sound_file(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    with StoreWorker(crawl.path) as worker:
        worker.insert(1, 2, 3)
        worker.flush()

        worker.kill()

    assert (query(crawl.path, "PRAGMA integrity_check"), query(crawl.path, COUNT)) == (
        [("ok",)],
        [(3,)],
    )


def test_a_killed_writer_loses_uncommitted_units(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    with StoreWorker(crawl.path) as worker:
        worker.insert(1, 2, 3)

        worker.kill()

    assert query(crawl.path, COUNT) == [(0,)]


def test_a_new_writer_opens_the_file_of_a_killed_writer_at_once(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    with StoreWorker(crawl.path) as worker:
        worker.insert(1, 2, 3)
        worker.flush()

        worker.kill()

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(4, "https://example.com/4"))

    assert (query(crawl.path, "PRAGMA integrity_check"), query(crawl.path, COUNT)) == (
        [("ok",)],
        [(4,)],
    )


def test_reading_during_a_write_in_wal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    with StoreWorker(crawl.path) as worker:
        worker.insert(1, 2, 3)
        worker.flush()
        # The same exclusive lock that shuts readers out in rollback-journal mode.
        worker.lock()

        seen = query(crawl.path, COUNT)

    assert seen == [(3,)]


def test_busy_in_rollback_journal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting="delete")
    workspace = current_workspace(temp_workspace)

    with StoreWorker(crawl.path) as worker:
        worker.lock()
        with pytest.raises(SpiderError) as raised:
            resolve_crawl(str(crawl.path), workspace=workspace, cwd=temp_workspace.root)

    assert (raised.value.code, raised.value.exit_code) == ("crawl_busy", 5)


def test_a_busy_writer_on_open(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting="delete")

    with StoreWorker(crawl.path) as worker:
        worker.lock()
        with pytest.raises(SpiderError) as raised:
            CrawlWriter(crawl.path, FakeClock(), busy_seconds=SHORT_BUSY_SECONDS)

    assert (raised.value.code, raised.value.exit_code, raised.value.diagnostic.details) == (
        "crawl_busy",
        5,
        {"file": str(crawl.path)},
    )


def test_a_busy_writer_in_a_unit(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, journal_setting="delete")

    def run_while_locked() -> None:
        with (
            CrawlWriter(crawl.path, FakeClock(), busy_seconds=SHORT_BUSY_SECONDS) as writer,
            StoreWorker(crawl.path) as worker,
        ):
            worker.lock()
            writer.run(insert_seed(9, "https://example.com/9"))

    # Around the writer's with block too: leaving it raises the same crawl_busy again.
    with pytest.raises(SpiderError) as raised:
        run_while_locked()

    assert (raised.value.code, raised.value.exit_code, raised.value.diagnostic.details) == (
        "crawl_busy",
        5,
        {"file": str(crawl.path)},
    )
