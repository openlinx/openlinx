"""The transactional writer (015-add-crawl-store, 017-speed-up-crawl-writer, crawl-store)."""

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Connection, func, select, update
from sqlalchemy.exc import IntegrityError

from spider.output.diagnostics import SpiderError
from spider.store.connections import connect
from spider.store.reading import reading
from spider.store.schema import seeds
from spider.store.writer import CrawlWriter, CrawlWriterClosedError, CrawlWriterReplayError
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
from tests.support.writer import executing, replay_now

SEEDS = "SELECT position, url FROM seeds ORDER BY position"
COUNT = "SELECT count(*) FROM seeds"
SETTINGS = ("temp_store", "cache_size", "mmap_size")


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
            executing(
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

    assert ([position for position, _ in seen], committed) == ([1, 2, 3], [3])


def close_after_a_replay(
    crawl_file: Path, unit: Callable[[Connection], object]
) -> CrawlWriterClosedError:
    """Runs the unit, then one that fails, so the unit runs again; returns close()'s error."""
    writer = CrawlWriter(crawl_file, FakeClock())
    writer.run(unit)
    with pytest.raises(ValueError, match=r"^bad$"):
        writer.run(raising_insert(9, ValueError("bad")))
    with pytest.raises(CrawlWriterClosedError, match=r"^The crawl writer is closed\.$") as closed:
        writer.close()
    return closed.value


def test_a_unit_that_fails_or_returns_differently_when_it_runs_again_ends_the_writer(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def counts_its_runs(connection: Connection) -> int:
        runs.append(1)
        insert_seed(1, "https://example.com/1")(connection)
        return len(runs)

    closed = close_after_a_replay(crawl.path, counts_its_runs)

    assert (query(crawl.path, SEEDS), type(closed.__cause__), str(closed.__cause__)) == (
        [],
        CrawlWriterReplayError,
        f"The unit {counts_its_runs.__qualname__} returned a different result when it ran again.",
    )


def test_a_unit_that_changes_a_different_number_of_rows_when_it_runs_again_ends_the_writer(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def inserts_more_each_run(connection: Connection) -> None:
        runs.append(len(runs) + 1)
        for position in runs:
            insert_seed(position, f"https://example.com/{position}")(connection)

    closed = close_after_a_replay(crawl.path, inserts_more_each_run)

    assert (query(crawl.path, SEEDS), str(closed.__cause__)) == (
        [],
        f"The unit {inserts_more_each_run.__qualname__} changed 2 rows instead of 1 when it ran"
        " again.",
    )


def test_a_unit_that_meets_a_full_file_when_it_runs_again_ends_the_writer(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def fills_the_file_when_run_again(connection: Connection) -> None:
        runs.append(1)
        if len(runs) > 1:
            pages: int = connection.exec_driver_sql("PRAGMA page_count").scalar_one()
            connection.exec_driver_sql(f"PRAGMA max_page_count = {pages}")
        insert_seed(1, "https://example.com/" + "x" * 100_000)(connection)

    closed = close_after_a_replay(crawl.path, fills_the_file_when_run_again)
    replayed = closed.__cause__
    full = getattr(getattr(replayed, "__cause__", None), "orig", None)

    assert (query(crawl.path, COUNT), str(replayed), getattr(full, "sqlite_errorcode", None)) == (
        [(0,)],
        f"The unit {fills_the_file_when_run_again.__qualname__} raised when it ran again.",
        sqlite3.SQLITE_FULL,
    )


def test_a_unit_after_a_replay_that_differs_learns_why_the_writer_ended(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def counts_its_runs(connection: Connection) -> int:
        runs.append(1)
        return len(runs)

    writer = CrawlWriter(crawl.path, FakeClock())
    writer.run(counts_its_runs)
    with pytest.raises(ValueError, match=r"^bad$"):
        writer.run(raising_insert(9, ValueError("bad")))
    with pytest.raises(CrawlWriterClosedError) as later:
        writer.run(count_seeds)
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert type(later.value.__cause__) is CrawlWriterReplayError


def test_replay_now_runs_the_units_since_the_last_commit_again(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def counted_insert(connection: Connection) -> None:
        runs.append(1)
        insert_seed(1, "https://example.com/1")(connection)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(counted_insert)
        replay_now(writer)
        seen = query(crawl.path, COUNT)

    assert (len(runs), seen) == (2, [(1,)])


def test_replay_now_fails_at_a_unit_that_runs_again_differently(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def counts_its_runs(connection: Connection) -> int:
        runs.append(1)
        return len(runs)

    writer = CrawlWriter(crawl.path, FakeClock())
    writer.run(counts_its_runs)
    with pytest.raises(CrawlWriterClosedError) as raised:
        replay_now(writer)
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert type(raised.value.__cause__) is CrawlWriterReplayError


def test_the_replay_runs_units_without_a_savepoint(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    statements: list[str] = []

    def traces_the_writer(connection: Connection) -> None:
        driver = cast(sqlite3.Connection, connection.connection.driver_connection)
        driver.set_trace_callback(statements.append)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(traces_the_writer)
        writer.run(insert_seed(1, "https://example.com/1"))
        replay_now(writer)

    inserts = [statement for statement in statements if statement.startswith("INSERT")]
    savepoints = [statement for statement in statements if "SAVEPOINT" in statement.upper()]
    assert (len(inserts), savepoints) == (2, [])


def add_a_deferred_reference(crawl_file: Path) -> None:
    """Adds tables whose reference is checked only at the commit, so the commit itself fails."""
    with closing(connect(crawl_file)) as connection:
        connection.executescript(
            "CREATE TABLE parents (id INTEGER PRIMARY KEY);"
            "CREATE TABLE children (parent INTEGER REFERENCES parents (id)"
            " DEFERRABLE INITIALLY DEFERRED);"
        )


def breaks_a_deferred_reference(connection: Connection) -> None:
    connection.exec_driver_sql("INSERT INTO children VALUES (9)")


def test_the_failing_unit_gets_its_own_error_when_the_replay_commit_fails(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    add_a_deferred_reference(crawl.path)

    closed = close_after_a_replay(crawl.path, breaks_a_deferred_reference)

    assert (query(crawl.path, "SELECT count(*) FROM children"), type(closed.__cause__)) == (
        [(0,)],
        IntegrityError,
    )


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


def test_a_read_through_the_writer_commits_nothing(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        run_inserts(writer, 3)
        count = writer.run(count_seeds)
        seen = query(crawl.path, COUNT)

    assert (count, seen) == (3, [(0,)])


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


def submit_inserts(writer: CrawlWriter, count: int) -> list[Future[int]]:
    """Submits units that insert the Seeds 1 to count and return their positions."""
    return [writer.submit(positioned_insert(position)) for position in range(1, count + 1)]


def positioned_insert(position: int) -> Callable[[Connection], int]:
    def unit(connection: Connection) -> int:
        insert_seed(position, f"https://example.com/{position}")(connection)
        return position

    return unit


def test_a_submitted_unit_waits_for_its_commit(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        submitted = submit_inserts(writer, 3)
        count = writer.run(count_seeds)
        pending = [not future.done() for future in submitted]

    assert (count, pending) == (3, [True, True, True])


def test_a_flush_resolves_the_submitted_units(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    submitted: list[Future[int]] = []
    done_at_commit: list[list[bool]] = []

    def on_commit(units: int) -> None:
        done_at_commit.append([future.done() for future in submitted])

    with CrawlWriter(crawl.path, FakeClock(), on_commit=on_commit) as writer:
        submitted.extend(submit_inserts(writer, 3))
        writer.flush()
        results = [future.result(timeout=0) for future in submitted]
        seen = query(crawl.path, COUNT)

    assert (results, seen, done_at_commit) == ([1, 2, 3], [(3,)], [[True, True, True]])


def test_a_failing_submitted_unit_fails_its_future(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        failing = writer.submit(raising_insert(1, ValueError("bad")))
        writer.flush()
        error = failing.exception(timeout=0)

    assert (type(error), str(error)) == (ValueError, "bad")


def test_a_replay_commit_resolves_the_units_before_a_failing_one(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    failing: list[Future[None]] = []
    failed_at_commit: list[bool] = []

    def on_commit(units: int) -> None:
        failed_at_commit.append(failing[0].done())

    with CrawlWriter(crawl.path, FakeClock(), on_commit=on_commit) as writer:
        submitted = submit_inserts(writer, 3)
        failing.append(writer.submit(raising_insert(4, ValueError("bad"))))
        failing[0].exception(timeout=10)
        results = [future.result(timeout=0) for future in submitted]

    assert (results, failed_at_commit) == ([1, 2, 3], [False])


def waits_for[T](
    hold: threading.Event, unit: Callable[[Connection], T]
) -> Callable[[Connection], T]:
    """Holds the writer inside the unit until the event is set."""

    def held(connection: Connection) -> T:
        hold.wait()
        return unit(connection)

    return held


def fill_the_window(
    writer: CrawlWriter, first: Callable[[Connection], object]
) -> list[Future[Any]]:
    """Submits the first unit, then units that insert the Seeds 2 to 2,000."""
    rest = (writer.submit(positioned_insert(position)) for position in range(2, 2001))
    return [writer.submit(first), *rest]


def test_a_full_window_holds_the_next_submit(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    log: list[str] = []
    hold = threading.Event()
    about_to_submit = threading.Event()

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        first = fill_the_window(writer, waits_for(hold, positioned_insert(1)))[0]
        # Runs before the commit frees any room in the window, unlike on_commit.
        first.add_done_callback(lambda _: log.append("committed"))

        def submit_one_more() -> None:
            about_to_submit.set()
            writer.submit(positioned_insert(2001))
            log.append("returned")

        submitter = threading.Thread(target=submit_one_more)
        submitter.start()
        about_to_submit.wait()
        log.append("released")
        hold.set()
        submitter.join()

    assert log == ["released", "committed", "returned"]


def finishes(action: Callable[[], object]) -> bool:
    """Runs the action on another thread, and says whether it ended within 10 s."""
    thread = threading.Thread(target=action, daemon=True)
    thread.start()
    thread.join(timeout=10)
    return not thread.is_alive()


def test_units_waited_for_with_run_take_no_room_in_the_window(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    hold = threading.Event()
    running = threading.Event()

    def held(connection: Connection) -> None:
        running.set()
        hold.wait()

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        runner = threading.Thread(target=writer.run, args=(held,))
        runner.start()
        running.wait()
        submitted = finishes(lambda: submit_inserts(writer, 2000))
        hold.set()
        runner.join()

    assert submitted


def test_a_failing_submitted_unit_frees_its_room_in_the_window(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        submitted = finishes(
            lambda: [writer.submit(raising_insert(1, ValueError("bad"))) for _ in range(2001)]
        )

    assert submitted


def test_a_failed_commit_fails_every_future_of_its_batch(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    add_a_deferred_reference(crawl.path)
    writer = CrawlWriter(crawl.path, FakeClock())
    submitted: list[Future[Any]] = [
        *submit_inserts(writer, 2),
        writer.submit(breaks_a_deferred_reference),
    ]
    with pytest.raises(IntegrityError, match=r"FOREIGN KEY constraint failed") as flushed:
        writer.flush()
    with pytest.raises(CrawlWriterClosedError) as later:
        writer.submit(count_seeds)
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert (
        [future.exception(timeout=0) is flushed.value for future in submitted],
        str(later.value),
    ) == ([True, True, True], "The crawl writer is closed.")


def test_a_submit_that_waits_for_room_wakes_when_the_writer_ends(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    add_a_deferred_reference(crawl.path)
    hold = threading.Event()
    about_to_submit = threading.Event()
    raised: list[BaseException] = []
    writer = CrawlWriter(crawl.path, FakeClock())
    # The 500th unit's commit fails while units 501 to 2,000 are still queued.
    submitted = fill_the_window(writer, waits_for(hold, breaks_a_deferred_reference))

    def submit_one_more() -> None:
        about_to_submit.set()
        try:
            writer.submit(count_seeds)
        except CrawlWriterClosedError as error:
            raised.append(error)

    submitter = threading.Thread(target=submit_one_more)
    submitter.start()
    about_to_submit.wait()
    hold.set()
    submitter.join()
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert (
        type(submitted[0].exception()),
        type(submitted[-1].exception()),
        [type(error) for error in raised],
    ) == (IntegrityError, CrawlWriterClosedError, [CrawlWriterClosedError])


def test_a_failed_timer_commit_fails_the_futures_of_its_batch(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    add_a_deferred_reference(crawl.path)
    clock = FakeClock()
    writer = CrawlWriter(crawl.path, clock)
    submitted = writer.submit(breaks_a_deferred_reference)
    writer.run(count_seeds)
    # No unit follows, so the idle check commits.
    clock.advance(1.0)
    error = submitted.exception(timeout=10)
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert type(error) is IntegrityError


def test_a_failed_replay_fails_the_futures_of_the_units_that_ran_again(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    runs: list[int] = []

    def counts_its_runs(connection: Connection) -> int:
        runs.append(1)
        return len(runs)

    writer = CrawlWriter(crawl.path, FakeClock())
    replayed = writer.submit(counts_its_runs)
    failing = writer.submit(raising_insert(9, ValueError("bad")))
    errors = (failing.exception(timeout=10), replayed.exception(timeout=10))
    with pytest.raises(CrawlWriterClosedError):
        writer.close()

    assert [type(error) for error in errors] == [ValueError, CrawlWriterReplayError]


async def test_a_unit_submitted_from_an_event_loop_is_resolved_at_its_commit(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    called_on: list[int] = []

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        submitted = await writer.submit_async(positioned_insert(1))
        submitted.add_done_callback(lambda _: called_on.append(threading.get_ident()))
        writer.flush()
        result = await submitted

    assert (result, submitted.get_loop() is asyncio.get_running_loop(), called_on) == (
        1,
        True,
        [threading.get_ident()],
    )


async def test_a_submit_from_an_event_loop_waits_for_room_without_blocking_it(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    hold = threading.Event()
    # Releases the writer if the loop is blocked, so that case fails instead of hanging.
    fallback = threading.Timer(10, hold.set)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        fill_the_window(writer, waits_for(hold, positioned_insert(1)))
        fallback.start()
        waiting = asyncio.create_task(writer.submit_async(positioned_insert(2001)))
        await asyncio.sleep(0)
        released_by_the_loop = not hold.is_set()
        hold.set()
        fallback.cancel()
        submitted = await waiting
        writer.flush()
        result = await submitted

    assert (released_by_the_loop, result) == (True, 2001)


def test_cancelling_a_submitted_unit_s_future_does_not_withdraw_it(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        cancelled = writer.submit(positioned_insert(1)).cancel()
        second = writer.submit(positioned_insert(2))
        writer.flush()
        seen = query(crawl.path, SEEDS)

    assert (cancelled, [position for position, _ in seen], second.result(timeout=0)) == (
        False,
        [1, 2],
        2,
    )


async def test_cancelling_a_submit_from_an_event_loop_only_drops_its_outcome(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        first = await writer.submit_async(positioned_insert(1))
        first.cancel()
        # The cancel reaches the writer's own Future on the loop's next turn.
        await asyncio.sleep(0)
        second = await writer.submit_async(positioned_insert(2))
        writer.flush()
        result = await second
        seen = query(crawl.path, SEEDS)

    assert (first.cancelled(), [position for position, _ in seen], result) == (True, [1, 2], 2)


def test_a_submit_after_close_fails_at_once(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)
    writer = CrawlWriter(crawl.path, FakeClock())
    writer.close()

    with pytest.raises(CrawlWriterClosedError, match=r"^The crawl writer is closed\.$"):
        writer.submit(count_seeds)


def test_a_unit_cannot_submit_to_its_own_writer(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with (
        CrawlWriter(crawl.path, FakeClock()) as writer,
        pytest.raises(
            RuntimeError, match=r"^A unit cannot submit work to the writer that runs it\.$"
        ),
    ):
        writer.run(lambda connection: writer.submit(count_seeds))


def connection_settings(connection: Connection) -> tuple[int, int, int]:
    """A unit that reads temp_store, cache_size and mmap_size."""
    return (
        connection.exec_driver_sql("PRAGMA temp_store").scalar_one(),
        connection.exec_driver_sql("PRAGMA cache_size").scalar_one(),
        connection.exec_driver_sql("PRAGMA mmap_size").scalar_one(),
    )


def test_the_writer_s_connection_settings_in_wal_mode(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        journal: str = writer.run(
            lambda connection: connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        )
        settings = writer.run(connection_settings)

    assert (journal, settings) == ("wal", (2, -65536, 268435456))


def test_readers_keep_sqlite_s_defaults(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with reading(crawl.path) as connection:
        settings = connection_settings(connection)
    with closing(sqlite3.connect(crawl.path)) as plain:
        defaults = tuple(plain.execute(f"PRAGMA {name}").fetchone()[0] for name in SETTINGS)

    assert settings == defaults
