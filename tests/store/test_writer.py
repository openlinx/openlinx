"""The transactional writer (015-add-crawl-store, crawl-store)."""

from collections.abc import Callable

import pytest
from sqlalchemy import Connection, func, insert, select, update

from spider.store.schema import seeds
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace

SEEDS = "SELECT position, url FROM seeds ORDER BY position"
COUNT = "SELECT count(*) FROM seeds"


def insert_seed(position: int, url: str) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        connection.execute(insert(seeds).values(position=position, url=url))

    return unit


def count_seeds(connection: Connection) -> int:
    return connection.execute(select(func.count()).select_from(seeds)).scalar_one()


def test_a_unit_sees_the_units_before_it(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        count = writer.run(count_seeds)

    assert count == 1


def test_a_unit_updates_a_row_of_an_earlier_unit(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        writer.run(
            lambda connection: connection.execute(
                update(seeds).where(seeds.c.position == 1).values(url="https://example.com/b")
            )
        )

    assert query(crawl.path, SEEDS) == [(1, "https://example.com/b")]


def failing_insert(position: int, url: str) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        insert_seed(position, url)(connection)
        raise ValueError("bad")

    return unit


def test_a_failing_unit_leaves_no_change(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with (
        CrawlWriter(crawl.path, FakeClock()) as writer,
        pytest.raises(ValueError, match=r"^bad$") as raised,
    ):
        writer.run(failing_insert(2, "https://example.com/b"))

    assert (raised.type, query(crawl.path, SEEDS)) == (ValueError, [])


def test_other_units_survive_a_failing_unit(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(failing_insert(2, "https://example.com/b"))
        writer.run(insert_seed(3, "https://example.com/c"))

    assert [position for position, _ in query(crawl.path, SEEDS)] == [1, 3]


def test_closing_commits_everything(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        for position in range(1, 1001):
            writer.run(insert_seed(position, f"https://example.com/{position}"))

    assert query(crawl.path, COUNT) == [(1000,)]


def run_inserts(writer: CrawlWriter, count: int) -> None:
    for position in range(1, count + 1):
        writer.run(insert_seed(position, f"https://example.com/{position}"))


def test_units_wait_for_the_batch(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 499)
        seen = query(crawl.path, COUNT)

    assert seen == [(0,)]


def test_the_500th_unit_commits_the_batch(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 500)
        seen = query(crawl.path, COUNT)

    assert seen == [(500,)]


def test_the_timer_commits(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])
    clock = FakeClock()

    with CrawlWriter(crawl.path, clock) as writer:
        run_inserts(writer, 3)
        clock.advance(1.0)
        # The next unit runs the timer check; the idle check every 50 ms calls the same code.
        writer.run(count_seeds)
        seen = query(crawl.path, COUNT)

    assert seen == [(3,)]


def test_a_flush_commits_at_once(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 3)
        writer.flush()
        seen = query(crawl.path, COUNT)

    assert seen == [(3,)]
