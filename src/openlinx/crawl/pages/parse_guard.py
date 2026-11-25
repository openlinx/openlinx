"""Watch the Crawl independently of the workers and confirm process exit."""

import asyncio
import multiprocessing
import os
import signal
import socket
import sys
from collections.abc import Callable
from contextlib import suppress
from multiprocessing.connection import _ConnectionBase, wait
from multiprocessing.process import BaseProcess
from time import monotonic
from typing import Any

import psutil

from openlinx.clock import SystemClock

if sys.platform != "win32":
    from openlinx.crawl.pages.parse_launch import PosixWorker

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


def wait_for_exit(process: BaseProcess, deadline: float, clock: SystemClock) -> bool:
    """Wait for a process status without relying on when its sentinel becomes readable."""
    # On POSIX the writer can close before exit or stay open after exit if inherited
    # by another process. Only exitcode confirms that this process has been reaped.
    sentinel_ready = False
    while process.exitcode is None:
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            return False
        if sentinel_ready:
            # A readable sentinel would immediately wake another wait.
            clock.sleep_in_thread(min(0.01, remaining))
        else:
            sentinel_ready = bool(wait([process.sentinel], min(_POLL_SECONDS, remaining)))
    return True


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


def _end_posix_workers(lease: _PipeEnd) -> None:
    """Catch children that enter the private group while the owner is dying."""
    if sys.platform != "win32":
        leader = os.getpid()
        expires = monotonic() + _CONTROL_SECONDS

        def kill_group_members() -> None:
            for pid in psutil.pids():
                if pid == leader:
                    continue
                with suppress(ProcessLookupError, psutil.NoSuchProcess):
                    worker = psutil.Process(pid)
                    if os.getpgid(pid) == leader:
                        worker.kill()

        while monotonic() < expires:
            kill_group_members()
            if lease.poll(_POLL_SECONDS):
                break
        # EOF means no launch can still be joining the group. Look once more for any
        # child whose lease closed just after the scan.
        kill_group_members()


def _guard(commands: _PipeEnd, identity: Owner, lease: _PipeEnd | None) -> None:
    """End workers even if the owner leaves open, inherited pipe endpoints."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    else:
        os.setpgid(0, 0)

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
            elif action != "ready":
                raise RuntimeError("Unexpected parse guard command.")
            commands.send_bytes(b"ok")
    except (EOFError, OSError):
        pass
    finally:
        for worker in workers.values():
            with suppress(psutil.NoSuchProcess):
                worker.kill()
        if lease is not None:
            _end_posix_workers(lease)
            lease.close()
        commands.close()


class Guard:
    """Register each worker identity before sending that worker anything to execute."""

    def __init__(self, clock: SystemClock) -> None:
        self._clock = clock
        self.owner: Owner = (os.getpid(), psutil.Process().create_time())
        self._process: BaseProcess | None = None
        self._commands: _PipeEnd | None = None
        self._lease: _PipeEnd | None = None
        self._transaction = asyncio.Lock()

    async def start(self) -> None:
        spawn = multiprocessing.get_context("spawn")
        commands, reader = spawn.Pipe()
        lease_reader = None
        if sys.platform != "win32":
            lease_reader, self._lease = spawn.Pipe(duplex=False)
        process = spawn.Process(
            target=_guard,
            args=(reader, self.owner, lease_reader),
            name="parse-worker-guard",
            daemon=True,
        )
        try:
            with self._clock.off_loop():
                await asyncio.to_thread(process.start)
        except Exception:
            commands.close()
            process.close()
            self._close_lease()
            raise
        finally:
            reader.close()
            if sys.platform != "win32" and lease_reader is not None:
                lease_reader.close()
        self._commands = commands
        self._process = process
        if sys.platform != "win32":
            await self._exchange("ready", 0, 0.0)

    def worker(
        self, target: Callable[..., None], args: tuple[object, ...], name: str
    ) -> BaseProcess:
        if sys.platform != "win32":
            if self._process is None or self._process.pid is None or self._lease is None:
                raise RuntimeError("The parse guard must have a group before launching a worker.")
            return PosixWorker(target, args, name, self._process.pid, self._lease.fileno())
        else:
            spawn = multiprocessing.get_context("spawn")
            return spawn.Process(target=target, args=args, name=name, daemon=True)

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
            raise RuntimeError(f"The parse guard did not acknowledge {action}.")

    def _close_lease(self) -> None:
        if self._lease is not None:
            self._lease.close()

    async def close(self) -> None:
        process = self._process
        commands = self._commands
        if process is None or commands is None:
            return
        self._close_lease()
        with suppress(OSError):
            commands.send(("close", 0, 0.0))
        commands.close()
        with self._clock.off_loop():
            await asyncio.to_thread(self._join, process)

    def _join(self, process: BaseProcess) -> None:
        if not wait_for_exit(process, self._clock.monotonic() + _CONTROL_SECONDS, self._clock):
            process.kill()
            if not wait_for_exit(process, self._clock.monotonic() + _CONTROL_SECONDS, self._clock):
                raise RuntimeError("The parse guard did not exit.")
        process.join(0)
        process.close()
