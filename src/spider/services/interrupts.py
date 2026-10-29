"""Interrupts stop a foreground Crawl through its stop flag (020-add-crawl-core D10)."""

import asyncio
import os
import signal
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from types import FrameType

from spider.crawl.engine.stop import StopSignal
from spider.output.codes import ExitCode


def _signals() -> tuple[signal.Signals, ...]:
    if sys.platform == "win32":  # pragma: win32 cover
        return (signal.SIGINT, signal.SIGBREAK)
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

    interrupts = 0

    def handler(_signum: int, _frame: FrameType | None) -> None:
        nonlocal interrupts
        interrupts += 1
        if interrupts > 1:
            # The second ends the process at once and writes nothing; the last committed unit
            # keeps the file consistent, and it stays running (design D10).
            os._exit(ExitCode.INTERRUPTED)
        # It runs between two bytecodes of the main thread, which may hold the stderr lock, so
        # it only schedules the stop, which writes the stopping event on the loop.
        loop.call_soon_threadsafe(stop.set, "interrupt")

    previous = {signum: signal.signal(signum, handler) for signum in _signals()}
    try:
        with _woken(loop):
            yield
    finally:
        for signum, earlier in previous.items():
            # None: a handler that Python did not install, which it cannot put back.
            signal.signal(signum, signal.SIG_DFL if earlier is None else earlier)


@contextmanager
def _woken(loop: asyncio.AbstractEventLoop) -> Iterator[None]:
    """Python runs a handler only once the main thread runs again, so a signal that another
    thread takes, or that lands just before select(), would wait for the loop's next timer:
    the loop watches the wakeup fd instead. Windows' proactor loop sets its own."""
    if sys.platform == "win32":  # pragma: win32 cover
        yield
    else:  # pragma: win32 no cover
        reader, writer = socket.socketpair()
        reader.setblocking(False)
        writer.setblocking(False)
        loop.add_reader(reader.fileno(), _drain, reader)
        # The fd that was there, an embedding app's or a test runner's, comes back after.
        earlier = signal.set_wakeup_fd(writer.fileno(), warn_on_full_buffer=False)
        try:
            yield
        finally:
            signal.set_wakeup_fd(earlier)
            loop.remove_reader(reader.fileno())
            reader.close()
            writer.close()


def _drain(reader: socket.socket) -> None:  # pragma: win32 no cover
    with suppress(BlockingIOError):
        while reader.recv(4096):
            pass
