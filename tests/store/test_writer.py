"""The transactional writer (015-add-crawl-store, 017-speed-up-crawl-writer, crawl-store)."""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from sqlalchemy import Connection, func, select, update

from spider.output.diagnostics import SpiderError
from spider.store.connections import connect
from spider.store.schema import seeds
from spider.store.writer import CrawlWriter, CrawlWriterClosedError
from tests.support.clock import FakeClock
from tests.support.crawls import (
    crawl_without_seeds,
    create_any_crawl,
    insert_seed,
    query,
    sha256_of,
)
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace

SEEDS = "SELECT position, url FROM seeds ORDER BY position"
COUNT = "SELECT count(*) FROM seeds"


def count_seeds(connection: Connection) -> int:
    return connection.execute(select(func.count()).select_from(seeds)).scalar_one()


def test_a_unit_sees_the_units_before_it(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        count = writer.run(count_seeds)

    assert count == 1


def test_a_unit_updates_a_row_of_an_earlier_unit(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        writer.run(
            lambda connection: connection.execute(
                update(seeds).where(seeds.c.position == 1).values(url="https://example.com/b")
            )
        )

    assert query(crawl.path, SEEDS) == [(1, "https://example.com/b")]


def raising_insert(position: int, error: BaseException) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        insert_seed(position, f"https://example.com/{position}")(connection)
        raise error

    return unit


def test_a_failing_unit_leaves_no_change(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with (
        CrawlWriter(crawl.path, FakeClock()) as writer,
        pytest.raises(ValueError, match=r"^bad$"),
    ):
        writer.run(raising_insert(2, ValueError("bad")))

    assert query(crawl.path, SEEDS) == []


def test_other_units_survive_a_failing_unit(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(raising_insert(2, ValueError("bad")))
        writer.run(insert_seed(3, "https://example.com/c"))

    assert [position for position, _ in query(crawl.path, SEEDS)] == [1, 3]


def test_a_failing_unit_commits_the_units_before_it(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    committed: list[int] = []

    with CrawlWriter(crawl.path, FakeClock(), on_commit=committed.append) as writer:
        run_inserts(writer, 3)
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(raising_insert(4, ValueError("bad")))
        seen = query(crawl.path, SEEDS)

    assert ([position for position, _ in seen], committed[:1]) == ([1, 2, 3], [3])


def test_a_unit_that_fails_in_the_replay_is_left_out_of_its_commit(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    committed: list[int] = []
    runs: list[int] = []

    def fails_when_run_again(connection: Connection) -> None:
        # Breaks the contract that a unit writes the same on every run.
        runs.append(len(runs))
        if len(runs) > 1:
            raise ValueError("again")
        insert_seed(2, "https://example.com/2")(connection)

    with CrawlWriter(crawl.path, FakeClock(), on_commit=committed.append) as writer:
        writer.run(insert_seed(1, "https://example.com/1"))
        writer.run(fails_when_run_again)
        writer.run(insert_seed(3, "https://example.com/3"))
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(raising_insert(4, ValueError("bad")))
        seen = query(crawl.path, SEEDS)

    assert ([position for position, _ in seen], committed[:1], len(runs)) == ([1, 3], [2], 2)


def test_a_unit_that_fails_half_way_after_other_units_leaves_no_change(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    def changes_an_earlier_unit_and_fails(connection: Connection) -> None:
        insert_seed(3, "https://example.com/c")(connection)
        connection.execute(
            update(seeds).where(seeds.c.position == 1).values(url="https://example.com/z")
        )
        raise ValueError("bad")

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        writer.run(insert_seed(2, "https://example.com/b"))
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(changes_an_earlier_unit_and_fails)

    assert query(crawl.path, SEEDS) == [(1, "https://example.com/a"), (2, "https://example.com/b")]


def counted_raising_insert(
    position: int, error: BaseException, runs: list[int]
) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        runs.append(position)
        raising_insert(position, error)(connection)

    return unit


def test_a_failing_unit_runs_once(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/1"))
        with pytest.raises(ValueError, match=r"^bad$"):
            writer.run(counted_raising_insert(2, ValueError("bad"), runs))

    assert runs == [2]


def test_closing_commits_everything(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 1000)

    assert query(crawl.path, COUNT) == [(1000,)]


def run_inserts(writer: CrawlWriter, count: int) -> None:
    for position in range(1, count + 1):
        writer.run(insert_seed(position, f"https://example.com/{position}"))


def test_units_wait_for_the_batch(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 499)
        seen = query(crawl.path, COUNT)

    assert seen == [(0,)]


def test_the_500th_unit_commits_the_batch(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 500)
        seen = query(crawl.path, COUNT)

    assert seen == [(500,)]


def test_the_timer_commits(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    clock = FakeClock()

    with CrawlWriter(crawl.path, clock) as writer:
        run_inserts(writer, 3)
        clock.advance(1.0)
        # The next unit runs the timer check; the idle check every 50 ms calls the same code.
        writer.run(count_seeds)
        seen = query(crawl.path, COUNT)

    assert seen == [(3,)]


def test_the_timer_commits_while_no_unit_arrives(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    clock = FakeClock()
    committed: list[int] = []
    observed = threading.Event()

    def on_commit(units: int) -> None:
        committed.append(units)
        observed.set()

    with CrawlWriter(crawl.path, clock, on_commit=on_commit) as writer:
        run_inserts(writer, 3)
        clock.advance(1.0)
        fired = observed.wait(timeout=10)
        seen = query(crawl.path, COUNT)

    assert (fired, seen, committed[:1]) == (True, [(3,)], [3])


def test_a_flush_commits_at_once(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 3)
        writer.flush()
        seen = query(crawl.path, COUNT)

    assert seen == [(3,)]


def test_a_read_only_crawl_file(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    before = sha256_of(crawl.path)

    with read_only_file(crawl.path), pytest.raises(SpiderError) as raised:
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


def numbered_insert(position: int) -> Callable[[Connection], int]:
    """Returns how many units ran before it, so the order units ran in can be read back."""

    def unit(connection: Connection) -> int:
        ran_before = count_seeds(connection)
        insert_seed(position, f"https://example.com/{position}")(connection)
        return ran_before

    return unit


def test_units_from_several_threads_never_interleave(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:

        def caller(number: int) -> list[int]:
            return [writer.run(numbered_insert(number * 1000 + n)) for n in range(50)]

        with ThreadPoolExecutor(max_workers=4) as pool:
            orders = list(pool.map(caller, range(4)))

    assert (
        all(order == sorted(order) for order in orders),
        sorted(index for order in orders for index in order),
    ) == (True, list(range(200)))


async def test_run_async_from_an_event_loop(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        await writer.run_async(insert_seed(1, "https://example.com/a"))
        count = await writer.run_async(count_seeds)

    assert count == 1


def test_closing_twice_is_allowed(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    writer = CrawlWriter(crawl.path, FakeClock())
    writer.run(insert_seed(1, "https://example.com/a"))

    writer.close()
    writer.close()

    assert query(crawl.path, COUNT) == [(1,)]


def test_a_unit_after_close_fails_at_once(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    writer = CrawlWriter(crawl.path, FakeClock())
    writer.close()

    with pytest.raises(CrawlWriterClosedError, match=r"^The crawl writer is closed\.$"):
        writer.run(count_seeds)


def test_an_interrupted_unit_runs_once_and_the_writer_goes_on(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        with pytest.raises(KeyboardInterrupt):
            writer.run(counted_raising_insert(2, KeyboardInterrupt(), runs))
        writer.run(insert_seed(3, "https://example.com/c"))

    assert ([position for position, _ in query(crawl.path, SEEDS)], runs) == ([1, 3], [2])


def test_closing_truncates_the_wal_while_a_reader_stays_open(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    wal = crawl.path.with_name(crawl.path.name + "-wal")

    with closing(connect(crawl.path, read_only=True)) as reader:
        reader.execute("SELECT count(*) FROM seeds").fetchall()
        with CrawlWriter(crawl.path, FakeClock()) as writer:
            run_inserts(writer, 3)
        size = wal.stat().st_size

    assert size == 0


def test_a_unit_cannot_wait_for_its_own_writer(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with (
        CrawlWriter(crawl.path, FakeClock()) as writer,
        pytest.raises(
            RuntimeError, match=r"^A unit cannot submit work to the writer that runs it\.$"
        ),
    ):
        writer.run(lambda connection: writer.run(count_seeds))
