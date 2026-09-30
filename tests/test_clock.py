"""`FakeClock` and `SystemClock` (designs D6 and D8 of 000-scaffold-project)."""

import time
from datetime import UTC, datetime, timedelta

from spider.clock import Clock, SystemClock
from tests.support.clock import FakeClock


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
