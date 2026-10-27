"""Politeness limits (020-add-crawl-core D7; seam 4)."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from spider.crawl.fetch.politeness import RateGate, RequestLimits, global_cap
from tests.support.clock import FakeClock


@pytest.mark.parametrize(("concurrency", "cap"), [(1, 20), (5, 20), (6, 24), (25, 100), (50, 100)])
def test_the_global_cap_is_four_times_the_concurrency_within_20_to_100(
    concurrency: int, cap: int
) -> None:
    assert global_cap(concurrency) == cap


async def _held(acquire: Callable[[], Awaitable[object]]) -> int:
    """How many times `acquire` succeeds before it would wait."""
    held = 0
    while True:
        try:
            async with asyncio.timeout(0):
                await acquire()
        except TimeoutError:
            return held
        held += 1


@pytest.mark.parametrize(
    ("concurrency", "backlog", "tasks", "requests"),
    [(1, 0, 20, 20), (5, 2, 22, 20), (10, 4, 44, 40), (50, 8, 108, 100)],
)
async def test_tasks_are_bounded_by_the_request_cap_plus_the_backlog(
    concurrency: int, backlog: int, tasks: int, requests: int
) -> None:
    limits = RequestLimits(concurrency, backlog)
    request = limits.request()

    assert (await _held(limits.reserve_task), await _held(request.acquire)) == (tasks, requests)


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
