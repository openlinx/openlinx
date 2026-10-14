"""Politeness limits (020-add-crawl-core D7; seam 4)."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from spider.crawl.politeness import RequestLimits, global_cap


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
