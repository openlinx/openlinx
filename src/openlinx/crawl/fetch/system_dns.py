"""Keep a probe's native DNS work cancellable and owned by its admission slot."""

import asyncio
import json
import socket
import sys
from contextlib import suppress
from pathlib import Path

from aiohttp.abc import ResolveResult

_WORKER = Path(__file__).with_name("_dns_worker.py")


async def resolve_system(host: str, port: int) -> list[ResolveResult]:
    """Resolve through the OS without leaving a blocking getaddrinfo on Runner's executor."""
    # A Windows venv launcher would own a second process that Process.kill cannot reach.
    executable = (
        getattr(sys, "_base_executable", sys.executable)
        if sys.platform == "win32"
        else sys.executable
    )
    started = asyncio.create_task(
        asyncio.create_subprocess_exec(
            executable,
            "-I",
            "-S",
            str(_WORKER),
            host,
            str(port),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    )
    try:
        # Keep a handle even if the deadline fires during process creation.
        child = await asyncio.shield(started)
        answer, _ = await child.communicate()
    except BaseException:
        cleanup = asyncio.create_task(_kill_and_reap(started))
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        cleanup.result()
        raise
    if child.returncode != 0:
        return []
    return [
        ResolveResult(
            hostname=host,
            host=ip,
            port=resolved_port,
            family=socket.AddressFamily(family),
            proto=proto,
            flags=socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
        )
        for ip, resolved_port, family, proto in json.loads(answer)
    ]


async def _kill_and_reap(started: asyncio.Task[asyncio.subprocess.Process]) -> None:
    try:
        child = await started
    except OSError:
        return  # A failed spawn created no child.
    with suppress(ProcessLookupError):
        child.kill()
    # Drain the pipe too: a child waiting for pipe space cannot be joined by wait alone.
    await child.communicate()
