"""The network pause owns request admission separately from slots (022 design D4)."""

import asyncio


class PauseGate:
    """Requests already waiting pass before newcomers after the pause ends."""

    def __init__(self) -> None:
        self._open = asyncio.Event()
        self._open.set()
        self._at_gate = 0
        self._gate_drained = asyncio.Event()

    def close(self) -> None:
        self._open.clear()

    def open(self) -> None:
        self._open.set()

    @property
    def is_open(self) -> bool:
        return self._open.is_set()

    async def pass_request(self, *, ends_at_gate: bool) -> bool:
        """Those that waited at the gate wake a loop turn or more after it opens: a request
        that comes since then goes behind them, so requests reach the host's slot in the order
        they were dispatched (design D1). False for one that `ends_at_gate` at a closed one."""
        while self._at_gate and (not ends_at_gate or self._open.is_set()):
            await self._gate_drained.wait()
        if self._open.is_set():
            return True
        if ends_at_gate:
            return False
        if not self._at_gate:
            self._gate_drained = asyncio.Event()
        self._at_gate += 1
        try:
            await self._open.wait()
        finally:
            self._at_gate -= 1
            if not self._at_gate:
                self._gate_drained.set()
        return True
