"""Send native Ctrl+Break inside a private console and observe spawn before its target."""

import json
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from threading import Event
from time import monotonic, sleep

import psutil

from tests.support.processes import python_command

if sys.platform == "win32":
    import _winapi
    import ctypes
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    _kernel.GetConsoleProcessList.restype = wintypes.DWORD
    _kernel.GetConsoleWindow.argtypes = []
    _kernel.GetConsoleWindow.restype = wintypes.HWND
    _kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    _kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        *([ctypes.POINTER(wintypes.FILETIME)] * 4),
    ]
    _kernel.GetProcessTimes.restype = wintypes.BOOL
    _window_visible = ctypes.WinDLL("user32").IsWindowVisible
    _window_visible.argtypes = [wintypes.HWND]
    _window_visible.restype = wintypes.BOOL


def _ready_marker(path: Path) -> Path:
    return path.with_name(f"{path.name}.ready")


def _record(path: Path, value: object) -> None:
    # Windows can expose a renamed file before the rename handle has closed.
    # Publish readiness after closing the data file and keep it stable for readers.
    path.write_text(json.dumps(value), encoding="ascii")
    _ready_marker(path).touch()


def read_record(path: Path, seconds: float = 20) -> str:
    """Read a console observation whose writer has closed its data file."""
    _await_file(_ready_marker(path), seconds)
    return path.read_text(encoding="ascii")


def _console_pids() -> list[int]:
    if sys.platform == "win32":
        size = 16
        while True:
            pids = (wintypes.DWORD * size)()
            count: int = _kernel.GetConsoleProcessList(pids, size)
            if count == 0:
                error = ctypes.get_last_error()
                if error == 6:  # ERROR_INVALID_HANDLE from a process with no console.
                    return []
                raise ctypes.WinError(error)
            if count <= size:
                return sorted(pids[:count])
            size = count
    raise RuntimeError("Console membership requires Windows")


def bootstrap_probe(folder: Path, env: dict[str, str], blocked: str, guard: str) -> None:
    """Install a child-only site hook before the multiprocessing command runs."""
    bootstrap = folder / "bootstrap_import"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(
        """
import os
import sys

if "--multiprocessing-fork" in sys.argv and "OPENLINX_TEST_SPAWN_NAME" in os.environ:
    from tests.crawl.parse_windows_console import observe_bootstrap

    observe_bootstrap()
""",
        encoding="utf-8",
    )
    # Exceed the default spawn pipe capacity before a child can read any preparation data.
    extra_paths = [str(folder / "unused" / f"{i:03d}" / ("x" * 90)) for i in range(85)]
    env["PYTHONPATH"] = os.pathsep.join([str(bootstrap), env["PYTHONPATH"], *extra_paths])
    env["OPENLINX_TEST_SPAWN_FOLDER"] = str(folder)
    env["OPENLINX_TEST_SPAWN_BLOCKED"] = blocked
    env["OPENLINX_TEST_SPAWN_GUARD"] = guard


def observe_bootstrap() -> None:
    if sys.platform == "win32":
        folder = Path(os.environ["OPENLINX_TEST_SPAWN_FOLDER"])
        name = os.environ["OPENLINX_TEST_SPAWN_NAME"]
        pid = os.getpid()
        for fd, stream in ((1, "stdout"), (2, "stderr")):
            with suppress(OSError):
                os.write(fd, f"{pid} {stream} before spawn\n".encode("ascii"))
        window = _kernel.GetConsoleWindow()
        _record(
            folder / name,
            {
                "pid": pid,
                "console_pids": _console_pids(),
                "window_visible": bool(window and _window_visible(window)),
            },
        )
        if name == os.environ["OPENLINX_TEST_SPAWN_BLOCKED"]:
            Event().wait()
        if name == os.environ["OPENLINX_TEST_SPAWN_GUARD"]:
            _await_file(folder / "release_guardian", 30)


def _await_file(path: Path, seconds: float) -> None:
    deadline = monotonic() + seconds
    while not path.exists():
        if monotonic() >= deadline:
            raise RuntimeError(f"Missing {path.name}")
        sleep(0.01)


@dataclass(frozen=True, kw_only=True)
class ConsoleCrawl:
    folder: Path
    broker: subprocess.Popen[bytes]
    owner_pid: int
    owner_handle: int
    handles: ExitStack
    children: set[psutil.Process]

    def watch(self, pid: int) -> int:
        if sys.platform == "win32":
            child = psutil.Process(pid)
            assert child.ppid() == self.owner_pid, f"{pid} is not a direct Crawl child"
            self.children.add(child)
            handle = _open_process(pid)
            self.handles.callback(_winapi.CloseHandle, handle)
            self.handles.callback(self._capture_status, handle, pid)
            return handle
        raise RuntimeError("Native process handles require Windows")

    def assert_parse_children(self, expected: set[int]) -> dict[int, tuple[int, str]]:
        """Account for every descendant while the owner and parse children are held."""
        if sys.platform == "win32":
            console_host = Path(os.environ["SYSTEMROOT"]) / "System32" / "conhost.exe"
            descendants = {}
            for child in psutil.Process(self.owner_pid).children(recursive=True):
                with suppress(psutil.NoSuchProcess):
                    descendants[child.pid] = (child.ppid(), child.exe())
            # Windows can report its console hosts in the same tree as the parse
            # interpreters. Require all held interpreters and account for every extra.
            assert all(Path(executable).is_absolute() for _, executable in descendants.values()), (
                descendants
            )
            parse_pids = {
                pid
                for pid, (_, executable) in descendants.items()
                if Path(executable) != console_host
            }
            assert parse_pids == expected, descendants
            return descendants
        raise RuntimeError("Native process identities require Windows")

    def _capture_status(self, handle: int, pid: int) -> None:
        if sys.platform == "win32":
            if _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0:
                status = self.exit_status(handle, 0)
                (self.folder / f"exit-{pid}").write_text(f"{status:#x}", encoding="ascii")

    def exit_status(self, handle: int, seconds: int) -> int:
        if sys.platform == "win32":
            assert _winapi.WaitForSingleObject(handle, seconds * 1000) == _winapi.WAIT_OBJECT_0
            return _winapi.GetExitCodeProcess(handle)
        raise RuntimeError("Native process status requires Windows")

    def child_exits(
        self, watched: dict[str, int], seconds: int
    ) -> dict[str, tuple[int, float] | None]:
        """Wait within one budget and measure from the native owner exit timestamp."""
        if sys.platform == "win32":
            assert _winapi.WaitForSingleObject(self.owner_handle, 0) == _winapi.WAIT_OBJECT_0
            owner_exit = _exit_time(self.owner_handle)
            deadline = monotonic() + seconds
            exits: dict[str, tuple[int, float] | None] = {}
            for role, handle in watched.items():
                remaining_ms = max(0, ceil((deadline - monotonic()) * 1000))
                wait = _winapi.WaitForSingleObject(handle, remaining_ms)
                if wait == _winapi.WAIT_OBJECT_0:
                    elapsed = (_exit_time(handle) - owner_exit) / 10_000_000
                    exits[role] = (_winapi.GetExitCodeProcess(handle), elapsed)
                else:
                    assert wait == _winapi.WAIT_TIMEOUT, (role, wait)
                    exits[role] = None
            return exits
        raise RuntimeError("Native process times require Windows")


def _exit_time(handle: int) -> int:
    if sys.platform == "win32":
        creation, exit_at, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not _kernel.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_at),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return (exit_at.dwHighDateTime << 32) | exit_at.dwLowDateTime
    raise RuntimeError("Native process times require Windows")


def _open_process(pid: int) -> int:
    if sys.platform == "win32":
        query_limited_information = 0x1000
        return _winapi.OpenProcess(query_limited_information | _winapi.SYNCHRONIZE, False, pid)
    raise RuntimeError("Native process handles require Windows")


@contextmanager
def private_console(
    folder: Path, argv: list[str], env: dict[str, str], delivery: str, *, repeat: bool = False
) -> Iterator[ConsoleCrawl]:
    if sys.platform == "win32":
        command = python_command(
            "-m",
            "tests.crawl.parse_windows_console",
            str(folder),
            delivery,
            "twice" if repeat else "once",
            *argv,
        )
        if command.env is not None:
            env = {**env, "__PYVENV_LAUNCHER__": command.env["__PYVENV_LAUNCHER__"]}
        startup = subprocess.STARTUPINFO(
            dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=subprocess.SW_HIDE
        )
        children: set[psutil.Process] = set()
        with (
            (folder / "stdout").open("wb") as stdout,
            (folder / "stderr").open("wb") as stderr,
            subprocess.Popen(
                command.argv,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup,
            ) as broker,
        ):
            broker_identity = psutil.Process(broker.pid)
            try:
                owner = int(read_record(folder / "owner_pid"))
                children.add(psutil.Process(owner))
                with ExitStack() as handles:
                    handle = _open_process(owner)
                    handles.callback(_winapi.CloseHandle, handle)
                    console = ConsoleCrawl(
                        folder=folder,
                        broker=broker,
                        owner_pid=owner,
                        owner_handle=handle,
                        handles=handles,
                        children=children,
                    )
                    handles.callback(console._capture_status, handle, owner)
                    yield console
            finally:
                with suppress(psutil.NoSuchProcess):
                    children.update(broker_identity.children(recursive=True))
                if broker.poll() is None:
                    broker.kill()
                    broker.wait(timeout=5)
                for child in children:
                    with suppress(psutil.NoSuchProcess):
                        child.kill()
                _, alive = psutil.wait_procs(children, timeout=5)
                assert not alive, f"private console left processes alive: {[p.pid for p in alive]}"
    else:
        raise RuntimeError("A private test console requires Windows")


def _broker(folder: Path, delivery: str, repeat: bool, argv: list[str]) -> int:
    if sys.platform == "win32":
        # The broker is the only test process on this console that receives a broadcast.
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
        with subprocess.Popen(
            argv,
            env=python_command().env,
            stdin=0,
            stdout=subprocess.PIPE,
            stderr=2,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        ) as owner:
            _record(folder / "owner_pid", owner.pid)
            try:
                _await_file(folder / "send_break", 30)
                members = _console_pids()
                assert {os.getpid(), owner.pid} <= set(members)
                _record(folder / "console_pids", members)
                group = 0 if delivery == "broadcast" else owner.pid
                if not _kernel.GenerateConsoleCtrlEvent(signal.CTRL_BREAK_EVENT, group):
                    raise ctypes.WinError(ctypes.get_last_error())
                if repeat:
                    _await_file(folder / "send_second_break", 30)
                    assert owner.poll() is None, "Crawl exited before the second Ctrl+Break"
                    _record(folder / "second_console_pids", _console_pids())
                    if not _kernel.GenerateConsoleCtrlEvent(signal.CTRL_BREAK_EVENT, group):
                        raise ctypes.WinError(ctypes.get_last_error())
                    _record(folder / "second_break_sent", group)
                stdout, _ = owner.communicate(timeout=40)
                os.write(1, stdout)
                return owner.returncode
            finally:
                if owner.poll() is None:
                    owner.kill()
    raise RuntimeError("Native Ctrl+Break requires Windows")


if __name__ == "__main__":
    raise SystemExit(_broker(Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "twice", sys.argv[4:]))
