"""Exercise foreground shutdown with PID identities and a real blocked Page."""

import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Collection
from contextlib import ExitStack, suppress
from errno import ENXIO
from pathlib import Path
from time import monotonic, monotonic_ns, sleep

import psutil
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
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
                stored_links = query(
                    file,
                    "SELECT target.url FROM links "
                    "JOIN urls AS source ON source.id = links.source_url_id "
                    "JOIN urls AS target ON target.id = links.target_url_id "
                    "WHERE source.url = ? ORDER BY links.ordinal",
                    [site.url("/")],
                )
                assert len(stored_links) == 30
                assert stored_links == [(site.url(path),) for path in linked_paths]
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
) -> tuple[Path, ServerHandle]:
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
            return file, server
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
    import _winapi
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


def _finished_linked_crawl(
    site: StartSite,
    folder: Path,
    *,
    flags: int = 0,
    visible_window_pids: Callable[[], set[int]] | None = None,
) -> None:
    linked_pages = {f"/p{number}": Page(body=f"Page {number}") for number in range(1, 30)}
    # Keep the Crawl active after the worker has prepared the Seed.
    linked_pages["/p30"] = Page(body="Last Page", delay=2)
    file, server = _finished_tree(
        site,
        folder,
        linked_pages=linked_pages,
        flags=flags,
        visible_window_pids=visible_window_pids,
    )
    rows = query(
        file,
        "SELECT urls.url, urls.parsed FROM pages LEFT JOIN urls ON urls.id = pages.url_id "
        "ORDER BY urls.url",
    )
    assert len(rows) == 31
    # The scenario fixes the Seed and 30 targets independently of the fixture's Links.
    expected_paths = sorted(("/", *(f"/p{number}" for number in range(1, 31))))
    assert rows == [(server.url(path), 1) for path in expected_paths]


@pytest.mark.slow
def test_the_opt_in_crawl_stores_the_seed_and_all_thirty_linked_pages(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    _finished_linked_crawl(fixture_site, tmp_path)


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Console windows exist only on Windows")
def test_parse_workers_open_no_console_window(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    """Qualify the opt-in pool until the installed CLI selects it by default."""
    if sys.platform == "win32":
        _finished_linked_crawl(
            fixture_site,
            tmp_path,
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


def _open_bootstrap_gate(path: Path) -> int:
    """Connect only once the worker has opened its end of the FIFO in sitecustomize."""
    if sys.platform != "win32":
        deadline = monotonic() + 20
        while monotonic() < deadline:
            try:
                return os.open(path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as error:
                if error.errno != ENXIO:
                    raise
            sleep(0.01)
    raise AssertionError("no worker entered the sitecustomize FIFO gate")


def _cleanup_interrupted_tree(
    process: subprocess.Popen[bytes], children: Collection[psutil.Process]
) -> None:
    remaining = set(children)
    if process.poll() is None:
        with suppress(psutil.NoSuchProcess):
            remaining.update(psutil.Process(process.pid).children(recursive=True))
        process.kill()
        process.wait(timeout=5)
    for child in remaining:
        if _running(child):
            with suppress(psutil.NoSuchProcess):
                child.kill()


def _assert_recovery_pages(fixture_site: StartSite, folder: Path) -> Path:
    folder.mkdir()
    file, server = _finished_tree(fixture_site, folder)
    assert query(
        file,
        "SELECT urls.url, urls.parsed FROM pages LEFT JOIN urls ON urls.id = pages.url_id "
        "ORDER BY urls.url",
    ) == [(server.url("/"), 1), (server.url("/held"), 1)]
    return file


def test_the_console_observer_waits_for_a_closed_record(tmp_path: Path) -> None:
    from tests.crawl.parse_windows_console import _record, read_record

    marker = tmp_path / "parse-worker-0"
    marker.write_text('{ "pid":', encoding="ascii")
    with pytest.raises(RuntimeError, match=r"Missing parse-worker-0\.ready"):
        read_record(marker, seconds=0)
    _record(marker, {"pid": 71})
    assert json.loads(read_record(marker, seconds=0)) == {"pid": 71}


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl+Break is a Windows console event")
@pytest.mark.parametrize("delivery", ["targeted", "broadcast"])
@pytest.mark.parametrize("phase", ["worker", "replacement", "guardian"])
def test_ctrl_break_ends_the_parse_tree_during_windows_bootstrap(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    phase: str,
    delivery: str,
) -> None:
    """Interrupt a private console before a selected spawn child can run its target."""
    if sys.platform == "win32":
        _windows_bootstrap_case(fixture_site, tmp_path, phase, delivery)


def _windows_bootstrap_site(site: StartSite) -> ServerHandle:
    seed = '<a href="/die">Crash</a><a href="/held">Pending</a>'
    return site(
        Site(
            routes={
                "/": Page(body=seed),
                "/die": Page(body="Crash"),
                "/held": Page(body="Pending", after="/die"),
            }
        )
    )


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl+Break is a Windows console event")
@pytest.mark.parametrize("delivery", ["targeted", "broadcast"])
@pytest.mark.parametrize("phase", ["worker", "replacement", "guardian"])
def test_a_second_ctrl_break_ends_the_parse_tree_during_windows_bootstrap(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    tmp_path: Path,
    phase: str,
    delivery: str,
    record_property: Callable[[str, object], None],
) -> None:
    """End the owner while the spawn handoff and the child's native bootstrap are held."""
    if sys.platform == "win32":
        _windows_owner_death_case(fixture_site, tmp_path, phase, delivery, record_property)


if sys.platform == "win32":

    def _windows_owner_death_case(
        fixture_site: StartSite,
        tmp_path: Path,
        phase: str,
        delivery: str,
        record_property: Callable[[str, object], None],
    ) -> None:
        from tests.crawl.parse_windows_console import bootstrap_probe, private_console, read_record

        site = _windows_bootstrap_site(fixture_site)
        guardian, initial, replacement = "parse-worker-guard", "parse-worker-0", "parse-worker-1"
        held = {"guardian": guardian, "worker": initial, "replacement": replacement}[phase]
        argv, env = _fixture_command(site.url("/"), tmp_path, f"windows_{phase}")
        bootstrap_probe(tmp_path, env, held, "")
        env["OPENLINX_TEST_SPAWN_HANDOFF"] = held
        urls = "SELECT url, fetch_state, parsed, parse_error FROM urls ORDER BY url"
        pages = (
            "SELECT urls.url, urls.parsed FROM pages JOIN urls ON urls.id = pages.url_id "
            "ORDER BY urls.url"
        )
        if phase == "replacement":
            expected_urls = [
                (site.url("/"), "fetched", 1, None),
                (site.url("/die"), "fetched", 0, "worker_crashed"),
                (site.url("/held"), "queued", 0, None),
            ]
            expected_pages = [(site.url("/"), 1), (site.url("/die"), 0)]
        else:
            expected_urls = [(site.url("/"), "queued", 0, None)]
            expected_pages = []

        with private_console(tmp_path, argv, env, delivery, repeat=True) as console:
            file = Path(_observed(tmp_path / "crawl_file"))
            members = {console.owner_pid, console.broker.pid}
            roles = {
                "guardian": (guardian,),
                "worker": (guardian, initial),
                "replacement": (guardian, initial, replacement),
            }[phase]
            watched = {}
            pids = {}
            for role in roles:
                probe = json.loads(read_record(tmp_path / role))
                pid = probe["pid"]
                pids[role] = pid
                watched[role] = console.watch(pid)
                assert not (members & set(probe["console_pids"])), probe
                assert not probe["window_visible"], probe
                if phase == "replacement" and role == initial:
                    (tmp_path / "crash_worker").touch()
                    assert console.exit_status(watched[role], 10) == 3
            assert int(read_record(tmp_path / "spawn_handoff")) == pids[held]
            assert len(set(pids.values())) == len(roles)
            active = {
                role: pid for role, pid in pids.items() if phase != "replacement" or role != initial
            }
            descendants = console.assert_parse_children(set(active.values()))
            record_property(
                "windows_bootstrap_processes",
                json.dumps(
                    {"owner_pid": console.owner_pid, "active": active, "descendants": descendants},
                    sort_keys=True,
                ),
            )
            committed_by = monotonic() + 5
            while (rows := query(file, urls)) != expected_urls:
                assert monotonic() < committed_by, rows
                sleep(0.01)
            assert query(file, pages) == expected_pages
            before = crawl_row(file)
            assert (before["state"], before["stop_reason"]) == ("running", None)
            assert _winapi.WaitForSingleObject(watched[held], 0) == _winapi.WAIT_TIMEOUT

            (tmp_path / "send_break").touch()
            assert _observed(tmp_path / "stopping") == "interrupt"
            assert _winapi.WaitForSingleObject(console.owner_handle, 0) == _winapi.WAIT_TIMEOUT
            assert _winapi.WaitForSingleObject(watched[held], 0) == _winapi.WAIT_TIMEOUT

            (tmp_path / "send_second_break").touch()
            group = 0 if delivery == "broadcast" else console.owner_pid
            assert json.loads(read_record(tmp_path / "second_break_sent", seconds=5)) == group
            assert console.exit_status(console.owner_handle, 10) == 130
            exits = console.child_exits(watched, 10)
            assert set(json.loads(read_record(tmp_path / "console_pids"))) == members
            assert set(json.loads(read_record(tmp_path / "second_console_pids"))) == members
            assert crawl_row(file) == before
            assert query(file, "SELECT url FROM seeds") == [(site.url("/"),)]
            assert query(file, urls) == expected_urls
            assert query(file, pages) == expected_pages
            late = {
                role: result for role, result in exits.items() if result is None or result[1] > 10
            }
            if not late:
                assert console.broker.wait(timeout=5) == 130
        assert _assert_recovery_pages(fixture_site, tmp_path / "recovery") != file
        assert not late, (
            f"parse children exceeded 10 s after owner exit: {late}; "
            f"observed exits {exits}; before interrupt {descendants}"
        )


def _windows_bootstrap_case(site: StartSite, folder: Path, phase: str, delivery: str) -> None:
    if sys.platform == "win32":
        from tests.crawl.parse_windows_console import bootstrap_probe, private_console, read_record

        server = _windows_bootstrap_site(site)
        first_worker, guardian = "parse-worker-0", "parse-worker-guard"
        blocked = "parse-worker-1" if phase == "replacement" else first_worker
        argv, env = _fixture_command(server.url("/"), folder, f"windows_{phase}")
        bootstrap_probe(folder, env, blocked, guardian if phase == "guardian" else "")
        with private_console(folder, argv, env, delivery) as console:
            file = Path(_observed(folder / "crawl_file"))
            guard_probe = json.loads(read_record(folder / guardian))
            work_probe = json.loads(read_record(folder / blocked))
            probes = [guard_probe, work_probe]
            assert guard_probe["pid"] != work_probe["pid"]
            guard_handle = console.watch(guard_probe["pid"])
            worker_handle = console.watch(work_probe["pid"])
            assert _winapi.WaitForSingleObject(guard_handle, 0) == _winapi.WAIT_TIMEOUT
            assert _winapi.WaitForSingleObject(worker_handle, 0) == _winapi.WAIT_TIMEOUT
            urls = "SELECT url, fetch_state, parsed, parse_error FROM urls ORDER BY url"
            if phase == "replacement":
                first_probe = json.loads(read_record(folder / first_worker))
                probes.append(first_probe)
                assert int(_observed(folder / "prepared")) == first_probe["pid"]
                assert first_probe["pid"] != work_probe["pid"]
                expected = [
                    (server.url("/"), "fetched", 1, None),
                    (server.url("/die"), "fetched", 0, "worker_crashed"),
                    (server.url("/held"), "queued", 0, None),
                ]
            else:
                expected = [(server.url("/"), "queued", 0, None)]
            committed_by = monotonic() + 5
            while (rows := query(file, urls)) != expected:
                assert monotonic() < committed_by, rows
                sleep(0.01)
            record = crawl_row(file)
            assert (record["state"], record["stop_reason"]) == ("running", None)

            visible_windows = _visible_windows()
            (folder / "send_break").touch()
            _await_windows_interrupt(folder, console.owner_handle, worker_handle, work_probe["pid"])
            assert (folder / "stopping").read_text(encoding="ascii") == "interrupt"
            assert console.exit_status(console.owner_handle, 0) == 130
            worker_status = console.exit_status(worker_handle, 10)
            guard_status = console.exit_status(guard_handle, 0)
            assert worker_status in (0x10000, signal.SIGTERM), (
                f"worker exited with {worker_status:#x}"
            )
            assert guard_status == 0, f"guardian exited with {guard_status:#x}"
            members = set(json.loads(read_record(folder / "console_pids")))
            assert members == {console.owner_pid, console.broker.pid}
            assert console.broker.wait(timeout=5) == 130
            streams = {
                name: (folder / name).read_text(encoding="utf-8") for name in ("stdout", "stderr")
            }
            for probe in probes:
                assert not ({console.owner_pid, console.broker.pid} & set(probe["console_pids"]))
                assert not probe["window_visible"], probe
                assert probe["pid"] not in visible_windows
                for stream, output in streams.items():
                    assert f"{probe['pid']} {stream} before spawn" in output
            record = crawl_row(file)
            assert (record["state"], record["stop_reason"]) == ("stopped", "interrupt")
            assert query(file, urls) == expected
            assert query(
                file,
                "SELECT urls.url, urls.parsed FROM pages JOIN urls ON urls.id = pages.url_id "
                "ORDER BY urls.url",
            ) == ([(server.url("/"), 1), (server.url("/die"), 0)] if phase == "replacement" else [])
        assert _assert_recovery_pages(site, folder / "recovery") != file


def _await_windows_interrupt(folder: Path, owner: int, worker: int, worker_pid: int) -> None:
    if sys.platform == "win32":
        shutdown_budget_ns = 14_000_000_000
        deadline = monotonic_ns() + shutdown_budget_ns
        stopping_observed_ns = None
        while _winapi.WaitForSingleObject(owner, 0) == _winapi.WAIT_TIMEOUT:
            now = monotonic_ns()
            if now >= deadline:
                if stopping_observed_ns is None:
                    raise AssertionError("Crawl did not confirm stopping=interrupt")
                (folder / "interrupt_timeout.json").write_text(
                    json.dumps(
                        {
                            "worker_pid": worker_pid,
                            "worker_wait": _winapi.WaitForSingleObject(worker, 0),
                            "stopping": "interrupt",
                            "stopping_observed_ns": stopping_observed_ns,
                            "worker_wait_started_ns": now,
                        }
                    ),
                    encoding="ascii",
                )
                raise AssertionError("Crawl did not exit after one interrupt")
            if stopping_observed_ns is None:
                with suppress(FileNotFoundError):
                    if (folder / "stopping").read_text(encoding="ascii") == "interrupt":
                        stopping_observed_ns = monotonic_ns()
                        deadline = stopping_observed_ns + shutdown_budget_ns
                        (folder / "release_guardian").touch()
            sleep(0.01)


@pytest.mark.slow
@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="Uses a POSIX bootstrap FIFO")
@pytest.mark.parametrize(
    "second_interrupt",
    [pytest.param(False, id="orderly-close"), pytest.param(True, id="parent-death")],
)
def test_owner_interrupts_end_a_worker_still_in_native_spawn_bootstrap(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path, second_interrupt: bool
) -> None:
    site = fixture_site(Site(routes={"/": Page(body="Bootstrap")}))
    fifo = tmp_path / "bootstrap_gate"
    if sys.platform != "win32":
        os.mkfifo(fifo)
    bootstrap = tmp_path / "bootstrap_import"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(
        """
import ctypes
import os
import sys
from pathlib import Path

def observe_group_sweep(folder):
    import psutil

    guardian = os.getpid()
    process_init = psutil.Process.__init__
    getpgid = os.getpgid

    def candidates():
        worker = int((folder / "worker_sitecustomize").read_text(encoding="ascii"))
        (folder / "swept").touch()
        return [0, guardian, worker]

    def check(pid):
        if pid in (0, guardian):
            (folder / "invalid_sweep_pid").write_text(str(pid), encoding="ascii")
            raise ProcessLookupError(pid)

    def observe_process(process, pid=None):
        check(pid)
        process_init(process, pid)

    def observe_group(pid):
        check(pid)
        return getpgid(pid)

    psutil.pids = candidates
    psutil.Process.__init__ = observe_process
    os.getpgid = observe_group

if "--multiprocessing-fork" in sys.argv:
    folder = Path(os.environ["OPENLINX_PROBE_BOOTSTRAP"])
    try:
        # The guardian reads its start payload before the owner can spawn the next child.
        with (folder / "guard_sitecustomize").open("x", encoding="ascii") as marker:
            marker.write(str(os.getpid()))
    except FileExistsError:
        try:
            with (folder / "bootstrap_gate").open("rb", buffering=0) as gate:
                (folder / "worker_sitecustomize").write_text(str(os.getpid()), encoding="ascii")
                ctypes.PyDLL(None).read(gate.fileno(), ctypes.create_string_buffer(1), 1)
        finally:
            # site ignores ordinary exceptions. An unexpected return must abort startup.
            raise SystemExit("The bootstrap gate returned before worker shutdown.")
    else:
        # Model macOS enumeration without looking up PID 0 or inspecting foreign processes.
        observe_group_sweep(folder)
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
    url_states = "SELECT url, fetch_state, parsed FROM urls"
    queued_seed = [(site.url("/"), "queued", 0)]
    children: list[psutil.Process] = []
    with (
        (tmp_path / "stderr").open("w+b") as stderr,
        subprocess.Popen(
            argv, env=env, stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True
        ) as process,
        ExitStack() as gate,
    ):
        try:
            file = Path(_observed(tmp_path / "crawl_file"))
            guard_pid = int(_observed(tmp_path / "guard_sitecustomize"))
            # The worker reports its identity after opening the reader. Keep the writer
            # open and empty so its native read cannot release the bootstrap gate.
            gate.callback(os.close, _open_bootstrap_gate(fifo))
            worker_pid = int(_observed(tmp_path / "worker_sitecustomize"))
            assert worker_pid != guard_pid
            children = psutil.Process(process.pid).children(recursive=True)
            worker = next(child for child in children if child.pid == worker_pid)
            guard = next(child for child in children if child.pid == guard_pid)
            if second_interrupt:
                # The actual OS start returned to the test barrier but its PID has not
                # reached the pool. The worker is stuck even before it can check admission.
                assert int(_observed(tmp_path / "spawned")) == worker_pid
                # Let the asynchronous writer commit the Seed before testing abrupt exit.
                committed_by = monotonic() + 5
                while (rows := query(file, url_states)) != queued_seed:
                    assert monotonic() < committed_by, rows
                    sleep(0.01)
            _is_blocked(worker)
            assert _running(guard)
            assert process.poll() is None
            assert not (tmp_path / "prepared").exists()
            deadline = monotonic() + 14
            process.send_signal(signal.SIGINT)
            assert _observed(tmp_path / "stopping") == "interrupt"
            _is_blocked(worker)
            if second_interrupt:
                assert process.poll() is None
                assert _running(guard)
                assert _running(worker)
                deadline = monotonic() + 2
                process.send_signal(signal.SIGINT)
            assert process.wait(timeout=deadline - monotonic()) == 130
            assert monotonic() < deadline
            try:
                _ended(children, 10)
            except AssertionError as error:
                other_pids = [child.pid for child in children if child not in (worker, guard)]
                error.add_note(f"worker={worker.pid}, guardian={guard.pid}, other={other_pids}")
                stderr_text = (tmp_path / "stderr").read_text(encoding="utf-8", errors="replace")
                error.add_note(f"Process stderr:\n{stderr_text[-8192:]}")
                raise
            assert (tmp_path / "swept").exists(), "the guardian did not sweep for workers"
            unexpected = tmp_path / "invalid_sweep_pid"
            assert not unexpected.exists(), f"the guardian inspected PID {unexpected.read_text()}"
            record = crawl_row(file)
            if second_interrupt:
                assert (record["state"], record["stop_reason"]) == ("running", None)
                assert query(file, "SELECT url FROM seeds") == [(site.url("/"),)]
                assert query(file, "SELECT url_id FROM pages") == []
            else:
                assert (record["state"], record["stop_reason"]) == ("stopped", "interrupt")
            assert query(file, url_states) == queued_seed
        finally:
            _cleanup_interrupted_tree(process, children)
    _assert_recovery_pages(fixture_site, tmp_path / "recovery")
