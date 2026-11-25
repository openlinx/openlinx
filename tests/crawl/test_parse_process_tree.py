"""Exercise foreground shutdown with PID identities and a real blocked Page."""

import os
import signal
import subprocess
import sys
from collections.abc import Callable, Collection
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


def _observed(path: Path, *, observe: Callable[[], None] | None = None) -> str:
    deadline = monotonic() + 20
    while monotonic() < deadline:
        if observe is not None:
            observe()
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


def _ended(children: Collection[psutil.Process], seconds: float) -> None:
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
    """Interrupt the opt-in Crawl while an observed worker is blocked."""
    first_link = "/die" if phase == "replacement" else "/hang"
    linked_paths = [first_link, *(f"/p{number}" for number in range(2, 31))]
    site = fixture_site(
        Site(
            routes={
                "/": Page(body="".join(f'<a href="{path}">Follow</a>' for path in linked_paths)),
                "/die": Page(body="Exit", headers=(("Link", "</hang>; rel=canonical"),)),
                "/hang": Page(body="Hung preparation"),
                **{path: Page(body="Linked Page") for path in linked_paths[1:]},
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
                assert query(
                    file,
                    "SELECT target.url FROM links "
                    "JOIN urls AS source ON source.id = links.source_url_id "
                    "JOIN urls AS target ON target.id = links.target_url_id "
                    "WHERE source.url = ? ORDER BY links.ordinal",
                    [site.url("/")],
                ) == [(site.url(path),) for path in linked_paths]
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
    site: StartSite,
    folder: Path,
    *,
    linked_pages: dict[str, Page] | None = None,
    flags: int = 0,
    visible_window_pids: Callable[[], set[int]] | None = None,
) -> None:
    if linked_pages is None:
        linked_pages = {"/held": Page(body="Second Page", delay=2)}
    seed = Page(body="".join(f'<a href="{path}">Follow</a>' for path in linked_pages))
    server = site(Site(routes={"/": seed, **linked_pages}))
    argv, env = _fixture_command(server.url("/"), folder, "complete")
    children: set[psutil.Process] = set()
    with (
        (folder / "stderr").open("w+b") as stderr,
        subprocess.Popen(
            argv, env=env, stdout=subprocess.DEVNULL, stderr=stderr, creationflags=flags
        ) as process,
    ):
        try:
            owner = psutil.Process(process.pid)

            def observe() -> None:
                current = owner.children(recursive=True)
                children.update(current)
                if visible_window_pids is not None:
                    windows = visible_window_pids() & {child.pid for child in current}
                    assert not windows, (
                        f"visible top-level windows owned by Crawl descendants: {sorted(windows)}"
                    )

            # Start watching before the fixture can spawn and keep watching through close.
            observe()
            (folder / "allow_start").touch()
            file = Path(_observed(folder / "crawl_file", observe=observe))
            prepared = int(_observed(folder / "prepared", observe=observe))
            worker = next((child for child in children if child.pid == prepared), None)
            assert worker is not None, f"parse worker {prepared} was not a Crawl descendant"
            assert _running(worker)
            assert _observed(folder / "closed", observe=observe) == "closed"
            assert process.poll() is None
            # The owner is still running, so its death cannot trigger the guardian.
            _ended([worker], 3)
            (folder / "allow_exit").touch()
            assert process.wait(timeout=20) == 0
            _ended(children, 10)
            assert crawl_row(file)["state"] == "completed"
            assert query(file, "SELECT url, parsed FROM urls ORDER BY url") == [
                (server.url(path), 1) for path in sorted(("/", *linked_pages))
            ]
        finally:
            if process.poll() is None:
                with suppress(psutil.NoSuchProcess):
                    children.update(psutil.Process(process.pid).children(recursive=True))
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

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _window_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_window_callback, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    def _visible_windows() -> set[int]:
        visible: set[int] = set()

        def found(window: int, _: int) -> bool:
            if _user32.IsWindowVisible(window):
                owner = wintypes.DWORD()
                if _user32.GetWindowThreadProcessId(window, ctypes.byref(owner)):
                    visible.add(owner.value)
            return True

        if not _user32.EnumWindows(_window_callback(found), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return visible


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Console windows exist only on Windows")
def test_parse_workers_open_no_console_window(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    """Qualify the opt-in pool until the installed CLI selects it by default."""
    if sys.platform == "win32":
        linked_pages = {f"/p{number}": Page(body=f"Page {number}") for number in range(1, 31)}
        # Keep the Crawl active after the worker has prepared the Seed.
        linked_pages["/p30"] = Page(body="Last Page", delay=2)
        _finished_tree(
            fixture_site,
            tmp_path,
            linked_pages=linked_pages,
            flags=subprocess.CREATE_NO_WINDOW,
            visible_window_pids=_visible_windows,
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


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "linux", reason="Observes Linux native bootstrap and spawn")
@pytest.mark.parametrize("second_interrupt", [False, True], ids=["orderly-close", "parent-death"])
def test_owner_interrupts_end_a_worker_still_in_native_spawn_bootstrap(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path, second_interrupt: bool
) -> None:
    site = fixture_site(Site(routes={"/": Page(body="Bootstrap")}))
    bootstrap = tmp_path / "bootstrap_import"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(
        """
import ctypes
import os
import sys
from pathlib import Path

if "--multiprocessing-fork" in sys.argv:
    folder = Path(os.environ["OPENLINX_PROBE_BOOTSTRAP"])
    try:
        # The guardian reads its start payload before the owner can spawn the next child.
        with (folder / "guard_sitecustomize").open("x", encoding="ascii") as marker:
            marker.write(str(os.getpid()))
    except FileExistsError:
        reader, writer = os.pipe()
        (folder / "worker_sitecustomize").write_text(str(os.getpid()), encoding="ascii")
        ctypes.PyDLL(None).read(reader, ctypes.create_string_buffer(1), 1)
""",
        encoding="utf-8",
    )
    phase = "bootstrap_handoff" if second_interrupt else "bootstrap_probe"
    argv, env = _fixture_command(site.url("/"), tmp_path, phase)
    # An ordinary long Python search path makes the stdlib's serialized preparation data
    # exceed a spawn pipe's buffer. Nothing reads it while the worker imports sitecustomize.
    search_path = [str(tmp_path / "unused" / f"{i:04d}" / ("x" * 176)) for i in range(340)]
    env["PYTHONPATH"] = os.pathsep.join([str(bootstrap), env["PYTHONPATH"], *search_path])
    env["OPENLINX_PROBE_BOOTSTRAP"] = str(tmp_path)
    children: list[psutil.Process] = []
    with (
        (tmp_path / "stderr").open("w+b") as stderr,
        subprocess.Popen(
            argv, env=env, stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True
        ) as process,
    ):
        try:
            file = Path(_observed(tmp_path / "crawl_file"))
            guard_pid = int(_observed(tmp_path / "guard_sitecustomize"))
            worker_pid = int(_observed(tmp_path / "worker_sitecustomize"))
            assert worker_pid != guard_pid
            children = psutil.Process(process.pid).children(recursive=True)
            worker = next(child for child in children if child.pid == worker_pid)
            guard = next(child for child in children if child.pid == guard_pid)
            if second_interrupt:
                # The actual OS start returned to the test barrier but its PID has not
                # reached the pool. The worker is stuck even before it can check admission.
                assert int(_observed(tmp_path / "spawned")) == worker_pid
            _is_blocked(worker)
            assert _running(guard)
            assert not (tmp_path / "prepared").exists()
            process.send_signal(signal.SIGINT)
            assert _observed(tmp_path / "stopping") == "interrupt"
            _is_blocked(worker)
            if second_interrupt:
                process.send_signal(signal.SIGINT)
                assert process.wait(timeout=2) == 130
                record = crawl_row(file)
                assert (record["state"], record["stop_reason"]) == ("running", None)
            else:
                assert process.wait(timeout=14) == 130
                record = crawl_row(file)
                assert (record["state"], record["stop_reason"]) == ("stopped", "interrupt")
                assert query(file, "SELECT url, fetch_state FROM urls") == [
                    (site.url("/"), "queued"),
                ]
            _ended(children, 10)
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
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    _finished_tree(fixture_site, recovery)
