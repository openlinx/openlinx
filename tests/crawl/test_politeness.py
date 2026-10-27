"""Politeness limits (020-add-crawl-core D7; seam 4)."""

import asyncio

import pytest

from spider.crawl.fetch.politeness import RateGate, global_cap
from tests.support.clock import FakeClock


@pytest.mark.parametrize(("concurrency", "cap"), [(1, 20), (5, 20), (6, 24), (25, 100), (50, 100)])
def test_the_global_cap_is_four_times_the_concurrency_within_20_to_100(
    concurrency: int, cap: int
) -> None:
    assert global_cap(concurrency) == cap


async def test_requests_that_the_global_cap_held_back_start_one_interval_apart() -> None:
    clock = FakeClock()
    gate = RateGate(clock, 2)
    turns, starts = [], []
    for _ in range(3):
        await gate.wait_turn("a.test")
        turns.append(clock.monotonic())
    # The cap lets all three through at 5 seconds.
    clock.advance(5 - clock.monotonic())
    for _ in range(3):
        await gate.started("a.test")
        starts.append(clock.monotonic())

    assert (turns, starts) == ([0.0, 0.5, 1.0], [5.0, 5.5, 6.0])


async def test_a_start_whose_wait_is_cancelled_is_given_back() -> None:
    clock = FakeClock()
    gate = RateGate(clock, 2)
    await gate.started("a.test")
    waiting = asyncio.create_task(gate.started("a.test"))
    # It takes the start at 0.5 and waits for it.
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    await gate.started("a.test")

    assert clock.monotonic() == 0.5
