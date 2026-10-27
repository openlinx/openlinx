"""`FakeClock` and `SystemClock` (designs D6 and D8 of 000-scaffold-project, D7 of
020-add-crawl-core)."""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection

from spider.clock import Clock, SystemClock
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace


def test_fake_clock_starts_at_new_year_2026_utc() -> None:
    assert FakeClock().now() == datetime(2026, 1, 1, tzinfo=UTC)


def test_advance_moves_wall_time_and_monotonic_time() -> None:
    clock = FakeClock()

    clock.advance(1.5)

    assert (clock.now(), clock.monotonic()) == (
        datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC),
        1.5,
    )


async def test_sleep_advances_virtual_time_without_waiting() -> None:
    clock: Clock = FakeClock()
    started = time.perf_counter()

    await clock.sleep(2)

    elapsed = time.perf_counter() - started
    assert (clock.monotonic(), elapsed < 0.1) == (2.0, True), f"real wait: {elapsed:.3f} s"


def test_system_clock_now_is_in_utc() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


def test_system_clock_monotonic_never_goes_back() -> None:
    clock: Clock = SystemClock()

    first = clock.monotonic()
    second = clock.monotonic()

    assert second >= first


async def test_system_clock_sleep_waits_in_real_time() -> None:
    clock: Clock = SystemClock()
    before = clock.monotonic()

    await clock.sleep(0.05)

    # Loose bound: on Windows a timer can fire up to ~16 ms early.
    assert clock.monotonic() - before >= 0.03


async def test_each_sleep_wakes_at_its_own_time() -> None:
    clock = FakeClock()
    woke: list[tuple[str, float]] = []

    async def nap(name: str, seconds: float) -> None:
        await clock.sleep(seconds)
        woke.append((name, clock.monotonic()))

    await asyncio.gather(nap("long", 1.0), nap("short", 0.5), nap("also short", 0.5))

    assert woke == [("short", 0.5), ("also short", 0.5), ("long", 1.0)]


async def test_the_clock_does_not_jump_while_the_writer_runs_a_unit_the_loop_waits_for(
    temp_workspace: TempWorkspace,
) -> None:
    crawl = create_any_crawl(temp_workspace)
    clock = FakeClock()
    release = threading.Event()

    def slow_read(connection: Connection) -> float:
        # A unit that takes real time on the writer's thread, as a large one does.
        release.wait(5)
        return clock.monotonic()

    with CrawlWriter(crawl.path, clock) as writer:
        # A deadline that is due once the loop has nothing else to do.
        pending = asyncio.ensure_future(clock.sleep(1))
        threading.Timer(0.2, release.set).start()
        seen = await writer.run_async(slow_read)
        await pending

    assert (seen, clock.monotonic()) == (0.0, 1.0)
