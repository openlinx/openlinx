"""Interrupts stop a foreground Crawl through its stop flag (020-add-crawl-core D10)."""

import asyncio
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

from spider.crawl.engine.stop import StopSignal


def _signals() -> tuple[signal.Signals, ...]:
    if sys.platform == "win32":  # pragma: win32 cover
        return (signal.SIGINT,)
    else:  # pragma: win32 no cover
        return (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


@contextmanager
def interrupts_stop(loop: asyncio.AbstractEventLoop, stop: StopSignal) -> Iterator[None]:
    """Entered after the Runner is built and before it runs: Runner.run puts its own SIGINT
    handler, which cancels the main task, only in place of the default one."""
    # signal.signal works only in the main thread; a Crawl run elsewhere keeps the process's.
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(_signum: int, _frame: FrameType | None) -> None:
        # It runs between two bytecodes of the main thread, which may hold the stderr lock, so
        # it only schedules the stop, which writes the stopping event on the loop.
        loop.call_soon_threadsafe(stop.set, "interrupt")

    previous = {signum: signal.signal(signum, handler) for signum in _signals()}
    try:
        yield
    finally:
        for signum, earlier in previous.items():
            # None: a handler that Python did not install, which it cannot put back.
            signal.signal(signum, signal.SIG_DFL if earlier is None else earlier)
