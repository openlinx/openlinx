"""The one event-loop factory for production and tests (design D15 of 000-scaffold-project)."""

import asyncio
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":  # pragma: win32 cover
        return asyncio.ProactorEventLoop()
    else:  # pragma: win32 no cover
        return asyncio.SelectorEventLoop()
