"""Share event-loop creation and cancellation-safe races between production and tests."""

import asyncio
import sys
from collections.abc import Awaitable, Collection
from typing import Any


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":  # pragma: win32 cover
        return asyncio.ProactorEventLoop()
    else:  # pragma: win32 no cover
        return asyncio.SelectorEventLoop()


async def first_of[T](
    work: Awaitable[T],
    *rivals: Awaitable[object],
    wake_on: Collection[asyncio.Future[Any]] = (),
) -> asyncio.Future[T]:
    """Runs `work` until it, a rival or one of `wake_on` ends, then cancels `work` and the
    rivals and waits until they have ended, so nothing they hold outlives the call. `wake_on`
    is only waited for, never cancelled. The result is `work`'s future: cancelled when it lost.
    """
    future = asyncio.ensure_future(work)
    others = [asyncio.ensure_future(rival) for rival in rivals]
    try:
        await asyncio.wait({future, *others, *wake_on}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        future.cancel()
        for other in others:
            other.cancel()
        await asyncio.wait({future, *others})
    return future
