"""Python processes that a test can kill (015-add-crawl-store)."""

import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from time import monotonic

import psutil


@dataclass(frozen=True)
class PythonCommand:
    argv: list[str]
    env: dict[str, str] | None


def python_command(*args: str) -> PythonCommand:
    base: str = getattr(sys, "_base_executable", sys.executable)
    if sys.platform == "win32" and sys.executable != base:
        # A venv's python.exe is a launcher that runs Python as its child, so a kill would miss
        # Python; the stdlib's multiprocessing starts the venv's base interpreter too (bpo-35797).
        env = {**os.environ, "__PYVENV_LAUNCHER__": sys.executable}
        return PythonCommand([base, *args], env)
    return PythonCommand([sys.executable, *args], None)


@contextmanager
def console_process(
    command: str,
    *,
    env: Mapping[str, str] | None,
    stdout: int,
    stderr: int,
    cleanup_timeout: float = 5.0,
) -> Iterator[subprocess.Popen[bytes]]:
    """Own a controlled Windows tree whose root waits for its children (030 task 12.3).

    Output goes to the caller's binary temporary files, never inherited pipes. The tree
    must not spawn after cleanup starts or lose its intermediate parents before discovery.
    """
    new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", None)
    if new_console is None:
        raise RuntimeError("console_process requires Windows")
    if cleanup_timeout <= 0:
        raise ValueError("cleanup_timeout must be positive")
    process: subprocess.Popen[bytes] = subprocess.Popen(
        f'cmd /d /s /c "{command}"',
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=new_console,
    )
    root: psutil.Process | None = None
    try:
        with suppress(psutil.NoSuchProcess):
            root = psutil.Process(process.pid)
            root.create_time()
        yield process
    finally:
        _end_console_tree(process, root, cleanup_timeout)


def _end_console_tree(
    process: subprocess.Popen[bytes], root: psutil.Process | None, timeout: float
) -> None:
    deadline = monotonic() + timeout
    owned: list[psutil.Process] = []
    if root is not None:
        owned.append(root)
        with suppress(psutil.NoSuchProcess):
            for child in root.children(recursive=True):
                child.create_time()
                owned.append(child)

    if owned and owned[0].is_running():
        # Leave time for the identity-based fallback if taskkill itself hangs.
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=min(timeout / 2, max(0, deadline - monotonic())),
                check=False,
            )
    for identity in reversed(owned):
        with suppress(psutil.NoSuchProcess):
            identity.kill()
    _, alive = psutil.wait_procs(owned, timeout=max(0, deadline - monotonic()))
    if alive:
        raise RuntimeError(
            f"console cleanup left processes alive: {[child.pid for child in alive]}"
        )
    process.wait(timeout=max(0, deadline - monotonic()))
