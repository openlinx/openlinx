"""The `Clock` every component that reads time takes (design D6 of 000-scaffold-project)."""

import asyncio
import time
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    def off_loop(self) -> AbstractContextManager[None]:
        """Held while the loop waits for work on another thread that finishes without
        clock time, such as a writer unit; a test's virtual clock does not jump meanwhile
        (020-add-crawl-core D7)."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def off_loop(self) -> AbstractContextManager[None]:
        return nullcontext()
