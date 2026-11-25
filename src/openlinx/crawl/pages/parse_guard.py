"""Watch the Crawl process independently of the parse workers and their pipes."""

import asyncio
import multiprocessing
import os
import signal
import socket
import sys
from contextlib import suppress
from multiprocessing.connection import _ConnectionBase, wait
from multiprocessing.process import BaseProcess
from typing import Any

import psutil

from openlinx.clock import Clock

type _PipeEnd = _ConnectionBase[Any, Any]
_POLL_SECONDS = 0.1
_CONTROL_SECONDS = 5.0
ADMISSION = b"\0"

type Owner = tuple[int, float]


def _same_process(pid: int, created: float) -> psutil.Process | None:
    with suppress(psutil.NoSuchProcess):
        process = psutil.Process(pid)
        if process.create_time() == created:
            return process
    return None


def _alive(process: psutil.Process) -> bool:
    with suppress(psutil.NoSuchProcess):
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    return False


def await_admission(channel: socket.socket, identity: Owner) -> bool:
    """Trust the snapshot only after enrolment and end if the owner dies before that."""
    owner = _same_process(*identity)
    if owner is None:
        return False
    channel.settimeout(_POLL_SECONDS)
    try:
        while _alive(owner):
            try:
                return channel.recv(1) == ADMISSION
            except TimeoutError:
                continue
    except OSError:
        return False
    finally:
        channel.settimeout(None)
    return False


def _guard(commands: _PipeEnd, identity: Owner) -> None:
    """End enrolled workers even if the owner leaves open, inherited pipe endpoints."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)

    owner = _same_process(*identity)
    workers: dict[int, psutil.Process] = {}
    try:
        while owner is not None and _alive(owner):
            if not commands.poll(_POLL_SECONDS):
                continue
            action, pid, born = commands.recv()
            if action == "close":
                break
            if action == "add":
                worker = _same_process(pid, born)
                if worker is not None:
                    workers[pid] = worker
            elif action == "remove":
                workers.pop(pid, None)
            else:
                raise RuntimeError("Unexpected parse guard command.")
            commands.send_bytes(b"ok")
    except (EOFError, OSError):
        pass
    finally:
        for worker in workers.values():
            with suppress(psutil.NoSuchProcess):
                worker.kill()
        commands.close()


class Guard:
    """Register each worker identity before sending that worker anything to execute."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self.owner: Owner = (os.getpid(), psutil.Process().create_time())
        self._process: BaseProcess | None = None
        self._commands: _PipeEnd | None = None
        self._transaction = asyncio.Lock()

    async def start(self) -> None:
        spawn = multiprocessing.get_context("spawn")
        commands, reader = spawn.Pipe()
        process = spawn.Process(
            target=_guard,
            args=(reader, self.owner),
            name="parse-worker-guard",
            daemon=True,
        )
        try:
            with self._clock.off_loop():
                await asyncio.to_thread(process.start)
        except Exception:
            commands.close()
            process.close()
            raise
        finally:
            reader.close()
        self._commands = commands
        self._process = process

    async def enroll(self, pid: int) -> None:
        try:
            born = psutil.Process(pid).create_time()
        except psutil.NoSuchProcess:
            return
        await self._exchange("add", pid, born)

    async def remove(self, pid: int) -> None:
        await self._exchange("remove", pid, 0.0)

    async def _exchange(self, action: str, pid: int, created: float) -> None:
        async with self._transaction:
            with self._clock.off_loop():
                await asyncio.to_thread(self._request, action, pid, created)

    def _request(self, action: str, pid: int, created: float) -> None:
        commands = self._commands
        process = self._process
        if commands is None or process is None:
            raise RuntimeError("The parse guard was not started.")
        commands.send((action, pid, created))
        ready = wait([commands, process.sentinel], _CONTROL_SECONDS)
        if commands not in ready or commands.recv_bytes() != b"ok":
            raise RuntimeError("The parse guard did not acknowledge a worker.")

    async def close(self) -> None:
        process = self._process
        commands = self._commands
        if process is None or commands is None:
            return
        with suppress(OSError):
            commands.send(("close", 0, 0.0))
        commands.close()
        with self._clock.off_loop():
            if not await asyncio.to_thread(wait, [process.sentinel], _CONTROL_SECONDS):
                process.kill()
            if not await asyncio.to_thread(wait, [process.sentinel], _CONTROL_SECONDS):
                raise RuntimeError("The parse guard did not exit.")
        process.join(0)
        process.close()
