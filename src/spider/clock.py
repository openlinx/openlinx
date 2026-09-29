"""The `Clock` every component that reads time takes (design D6 of 000-scaffold-project)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...
