"""Durability across a killed writer process (015-add-crawl-store, crawl-store)."""

from tests.support.crawls import crawl_without_seeds, query
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
