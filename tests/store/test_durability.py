"""Durability across a killed writer process (015-add-crawl-store, crawl-store)."""

from contextlib import closing

import pytest

from spider.output.diagnostics import SpiderError
from spider.store.connections import connect
from spider.store.selection import resolve_crawl
from tests.support.crawls import (
    crawl_without_seeds,
    create_any_crawl,
    current_workspace,
    query,
)
from tests.support.store_worker import StoreWorker
from tests.support.workspace import TempWorkspace

COUNT = "SELECT count(*) FROM seeds"


def test_a_killed_writer_keeps_committed_units_in_a_sound_file(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    worker = StoreWorker(crawl.path)
    for position in (1, 2, 3):
        worker.send(f"insert {position}")
    worker.send("flush")

    worker.kill()

    assert (query(crawl.path, "PRAGMA integrity_check"), query(crawl.path, COUNT)) == (
        [("ok",)],
        [(3,)],
    )


def test_a_killed_writer_loses_uncommitted_units(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    worker = StoreWorker(crawl.path)
    for position in (1, 2, 3):
        worker.send(f"insert {position}")

    worker.kill()

    assert query(crawl.path, COUNT) == [(0,)]


def test_reading_during_a_write_in_wal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    worker = StoreWorker(crawl.path)
    for position in (1, 2, 3):
        worker.send(f"insert {position}")
    worker.send("flush")

    seen = query(crawl.path, COUNT)
    worker.kill()

    assert seen == [(3,)]


@pytest.mark.slow
def test_busy_in_rollback_journal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    with closing(connect(crawl.path)) as connection:
        connection.execute("PRAGMA journal_mode = DELETE")
    worker = StoreWorker(crawl.path)
    worker.send("lock")

    with pytest.raises(SpiderError) as raised:
        resolve_crawl(
            str(crawl.path), workspace=current_workspace(temp_workspace), cwd=temp_workspace.root
        )
    worker.kill()

    assert (raised.value.code, raised.value.exit_code) == ("crawl_busy", 5)
