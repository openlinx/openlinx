"""`FakeClock` and `SystemClock` (designs D6 and D8 of 000-scaffold-project)."""

from datetime import UTC, datetime

from tests.support.clock import FakeClock


def test_fake_clock_starts_at_new_year_2026_utc() -> None:
    assert FakeClock().now() == datetime(2026, 1, 1, tzinfo=UTC)


def test_advance_moves_the_fake_clock_forward() -> None:
    clock = FakeClock()

    clock.advance(1.5)

    assert clock.now() == datetime(2026, 1, 1, 0, 0, 1, 500000, tzinfo=UTC)
