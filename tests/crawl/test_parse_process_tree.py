"""Exercise foreground shutdown with PID identities and a real blocked Page."""

import os
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from time import monotonic, sleep

import psutil
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import REPO_ROOT
from tests.support.crawls import crawl_row, query
from tests.support.processes import python_command
from tests.support.workspace import TempWorkspace


def _fixture_command(url: str, folder: Path, phase: str) -> tuple[list[str], dict[str, str]]:
    command = python_command("-m", "tests.crawl.parse_process_fixture", url, str(folder), phase)
    pythonpath = os.pathsep.join((str(REPO_ROOT / "src"), str(REPO_ROOT)))
    return command.argv, {**(command.env or os.environ), "PYTHONPATH": pythonpath}


def _observed(path: Path) -> str:
    deadline = monotonic() + 20
    while monotonic() < deadline:
        with suppress(FileNotFoundError):
            if value := path.read_text(encoding="utf-8"):
                return value
        sleep(0.01)
    raise AssertionError(f"missing observation: {path.name}")


def _interrupt(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(process.pid, signal.SIGINT)


def _running(process: psutil.Process) -> bool:
    with suppress(psutil.NoSuchProcess):
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    return False


def _ended(children: list[psutil.Process], seconds: float) -> None:
    deadline = monotonic() + seconds
    while monotonic() < deadline and any(map(_running, children)):
        sleep(0.01)
    assert [p.pid for p in children if _running(p)] == []


def _is_blocked(worker: psutil.Process) -> None:
    if sys.platform == "linux":
        deadline = monotonic() + 5
        while monotonic() < deadline:
            if "pipe_read" in Path(f"/proc/{worker.pid}/wchan").read_text(encoding="ascii"):
                return
            sleep(0.01)
        raise AssertionError(f"worker {worker.pid} did not enter native read")
    else:
        assert _running(worker)


@pytest.mark.slow
@pytest.mark.parametrize("phase", ["grace", "replacement", "starting"])
def test_an_interrupt_ends_the_parse_workers(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path, phase: str
) -> None:
    first_link = "/die" if phase == "replacement" else "/hang"
    site = fixture_site(
        Site(
            routes={
                "/": Page(body=f'<a href="{first_link}">Follow</a>'),
                "/die": Page(body="Exit", headers=(("Link", "</hang>; rel=canonical"),)),
                "/hang": Page(body="Hung preparation"),
            }
        )
    )
    argv, env = _fixture_command(site.url("/"), tmp_path, phase)
    if sys.platform == "win32":
        group = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        group = 0
    children: list[psutil.Process] = []
    with (
        (tmp_path / "stderr").open("w+b") as stderr,
        subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            creationflags=group,
            start_new_session=sys.platform != "win32",
        ) as process,
    ):
        try:
            owner = psutil.Process(process.pid)
            file = Path(_observed(tmp_path / "crawl_file"))
            worker_pid = int(_observed(tmp_path / "blocked"))
            children = owner.children(recursive=True)
            worker = next(p for p in children if p.pid == worker_pid)
            _is_blocked(worker)
            if phase != "starting":
                first_pid = int(_observed(tmp_path / "prepared"))
                if phase == "replacement":
                    assert worker.pid != first_pid
                    deadline = monotonic() + 5
                    while query(
                        file,
                        "SELECT parse_error FROM urls WHERE url = ?",
                        [
                            site.url("/die"),
                        ],
                    ) != [("worker_crashed",)]:
                        assert monotonic() < deadline
                        sleep(0.01)
                else:
                    assert worker.pid == first_pid
            started = monotonic()
            _interrupt(process)
            assert _observed(tmp_path / "stopping") == "interrupt"
            assert _running(worker)
            if phase != "grace":
                started = monotonic()
                _interrupt(process)
            assert process.wait(timeout=14 if phase == "grace" else 2) == 130
            if phase == "grace":
                assert 9 <= monotonic() - started < 14
            _ended(children, 10)
            record = crawl_row(file)
            if phase == "grace":
                assert (record["state"], record["stop_reason"]) == ("stopped", "interrupt")
                assert query(
                    file,
                    "SELECT fetch_state FROM urls WHERE url = ?",
                    [
                        site.url("/hang"),
                    ],
                ) == [("queued",)]
            else:
                assert (record["state"], record["stop_reason"]) == ("running", None)
        finally:
            if process.poll() is None:
                with suppress(psutil.NoSuchProcess):
                    children.extend(psutil.Process(process.pid).children(recursive=True))
                process.kill()
                process.wait(timeout=5)
            for child in children:
                if _running(child):
                    with suppress(psutil.NoSuchProcess):
                        child.kill()


def _finished_tree(
    site: StartSite, folder: Path, *, flags: int = 0, check_windows: bool = False
) -> None:
    server = site(
        Site(
            routes={
                "/": Page(body='<a href="/held">Follow</a>'),
                "/held": Page(body="Second Page", delay=2),
            }
        )
    )
    argv, env = _fixture_command(server.url("/"), folder, "complete")
    children: list[psutil.Process] = []
    windows: set[int] = set()
    with (
        (folder / "stderr").open("w+b") as stderr,
        subprocess.Popen(
            argv, env=env, stdout=subprocess.DEVNULL, stderr=stderr, creationflags=flags
        ) as process,
    ):
        try:
            owner = psutil.Process(process.pid)
            file = Path(_observed(folder / "crawl_file"))
            prepared = int(_observed(folder / "prepared"))
            children = owner.children(recursive=True)
            assert prepared in {child.pid for child in children}
            if sys.platform == "win32" and check_windows:
                windows = _visible_windows() & {child.pid for child in children}
            assert _observed(folder / "closed") == "closed"
            assert process.poll() is None
            # The owner is still running, so its death cannot trigger the guardian.
            _ended([child for child in children if child.pid == prepared], 3)
            (folder / "allow_exit").touch()
            assert process.wait(timeout=20) == 0
            _ended(children, 10)
            assert crawl_row(file)["state"] == "completed"
            assert query(file, "SELECT url, parsed FROM urls ORDER BY url") == [
                (server.url("/"), 1),
                (server.url("/held"), 1),
            ]
            assert windows == set()
        finally:
            if process.poll() is None:
                with suppress(psutil.NoSuchProcess):
                    children.extend(psutil.Process(process.pid).children(recursive=True))
                process.kill()
                process.wait(timeout=5)
            for child in children:
                if _running(child):
                    with suppress(psutil.NoSuchProcess):
                        child.kill()


@pytest.mark.slow
def test_no_parse_worker_outlives_a_completed_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    _finished_tree(fixture_site, tmp_path)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def _visible_windows() -> set[int]:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        visible: set[int] = set()

        def found(window: int, _: int) -> bool:
            if user32.IsWindowVisible(window):
                owner = wintypes.DWORD()
                user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
                visible.add(owner.value)
            return True

        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(found)
        user32.EnumWindows(callback, 0)
        return visible


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Console windows exist only on Windows")
def test_parse_workers_open_no_console_window(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    if sys.platform == "win32":
        _finished_tree(
            fixture_site, tmp_path, flags=subprocess.CREATE_NO_WINDOW, check_windows=True
        )


@pytest.mark.skipif(sys.platform != "linux", reason="Observes Linux descriptors and native waits")
def test_owner_death_ends_a_child_before_worker_admission(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    site = fixture_site(Site(routes={"/": Page(body="Page")}))
    argv, env = _fixture_command(site.url("/"), tmp_path, "pre_admission")
    children: list[psutil.Process] = []
    with (
        (tmp_path / "stderr").open("w+b") as stderr,
        subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=stderr) as owner,
    ):
        try:
            worker_pid = int(_observed(tmp_path / "spawned"))
            retained_pid = int(_observed(tmp_path / "retained"))
            children = psutil.Process(owner.pid).children(recursive=True)
            worker = next(child for child in children if child.pid == worker_pid)
            retained = next(child for child in children if child.pid == retained_pid)
            deadline = monotonic() + 5
            while not any(
                name in Path(f"/proc/{worker_pid}/wchan").read_text(encoding="ascii")
                for name in ("unix_stream", "poll_schedule")
            ):
                assert monotonic() < deadline
                sleep(0.01)
            worker_sockets = {
                path.readlink()
                for path in Path(f"/proc/{worker_pid}/fd").iterdir()
                if path.is_symlink()
            }
            owner_sockets = {
                path.readlink()
                for path in Path(f"/proc/{owner.pid}/fd").iterdir()
                if path.is_symlink()
            }
            retained_sockets = {
                path.readlink()
                for path in Path(f"/proc/{retained_pid}/fd").iterdir()
                if path.is_symlink()
            }
            assert {link for link in retained_sockets & owner_sockets if "socket:" in str(link)}
            assert {link for link in worker_sockets if "socket:" in str(link)}
            assert _running(worker)
            assert not (tmp_path / "prepared").exists()
            owner.kill()
            assert owner.wait(timeout=2) == -9
            _ended([child for child in children if child.pid != retained.pid], 3)
            assert _running(retained)
        finally:
            if owner.poll() is None:
                with suppress(psutil.NoSuchProcess):
                    children.extend(psutil.Process(owner.pid).children(recursive=True))
                owner.kill()
                owner.wait(timeout=5)
            for child in children:
                if _running(child):
                    with suppress(psutil.NoSuchProcess):
                        child.kill()
