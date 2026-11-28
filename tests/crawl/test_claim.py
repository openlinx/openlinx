"""Observe the Crawl Service holding its OS writer claim through work and releasing it on exit."""

import asyncio
import errno
import os
import re
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing, nullcontext
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from shutil import copyfile
from typing import Any, Literal
from urllib.parse import urlsplit

import pytest
from sqlalchemy import Engine, ExceptionContext, event

from openlinx.clock import SystemClock
from openlinx.crawl.engine.hooks import Hooks, Pass, PassContext
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides, continue_crawl
from openlinx.services.crawls import create_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.selection import resolve_crawl
from openlinx.workspace.discovery import resolve_workspace
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Route, Site
from tests.support.cli import PROCESS_TIMEOUT, await_event, start_cli_process
from tests.support.clock import FakeClock
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import STARTED_AT, current_workspace, new_crawl, query
from tests.support.network import closed_port
from tests.support.permissions import read_only_file
from tests.support.processes import python_command
from tests.support.randomness import scripted_choice
from tests.support.sqlite_faults import disk_full_after
from tests.support.workspace import TempWorkspace

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

_CLAIM_OPEN_FAILED = r"\b(?:cannot|could not|unable to) open (?:the )?writer claim\b"

# Independent of the claim implementation: this probe must also run before it exists.
_PROBE = """
import errno
import sys

with open(sys.argv[1], "a+b") as file:
    if sys.platform == "win32":
        import msvcrt
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            sys.exit(10)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            sys.exit(10)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
"""


def _probe_claim(lock_file: Path) -> int:
    # This OS check needs no site packages or subprocess coverage startup.
    command = python_command("-I", "-S", "-c", _PROBE, str(lock_file))
    probe = subprocess.run(
        command.argv,
        env=command.env,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    assert probe.returncode in (0, 10), probe.stderr
    return probe.returncode


@pytest.mark.slow
def test_a_running_crawl_keeps_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body="<p>Waiting</p>", hang=True),
                "/probe-ready": Page(body="ready", after="/"),
            }
        )
    )
    process = start_cli_process("crawl", server.url("/"))
    try:
        started = await_event(process, "crawl_started")
        crawl_file = Path(started["crawl_file"])
        lock_file = crawl_file.with_name(f"{started['crawl_id']}.lock")
        # crawl_started precedes the writer opening; the HTTP handshake proves it is running.
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            connection.request("GET", "/probe-ready")
            with connection.getresponse() as response:
                assert (response.status, response.read()) == (200, b"ready")

        assert (_probe_claim(lock_file), process.poll()) == (10, None)
        selected = resolve_crawl(
            started["crawl_id"],
            workspace=current_workspace(temp_workspace),
            cwd=temp_workspace.root,
        )
        before = query(crawl_file, "SELECT state, config FROM crawl")
        requests = server.requests
        reporter = Collected()

        with pytest.raises(OpenLinxError) as refused:
            continue_crawl(selected, CrawlOverrides(), SystemClock(), reporter, default_hooks())

        diagnostic = refused.value.diagnostic
        assert (refused.value.code, refused.value.exit_code, diagnostic.details) == (
            "crawl_locked",
            5,
            {"file": str(crawl_file)},
        )
        assert diagnostic.hint is not None
        assert f"linx status --crawl {selected.id}" in diagnostic.hint
        assert query(crawl_file, "SELECT state, config FROM crawl") == before
        assert (reporter.events, server.requests) == ([], requests)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=PROCESS_TIMEOUT)


@pytest.mark.slow
def test_a_killed_crawl_releases_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body="<p>Waiting</p>", hang=True),
                "/probe-ready": Page(body="ready", after="/"),
            }
        )
    )
    process = start_cli_process("crawl", server.url("/"))
    try:
        started = await_event(process, "crawl_started")
        crawl_file = Path(started["crawl_file"])
        lock_file = crawl_file.with_name(f"{started['crawl_id']}.lock")
        # crawl_started precedes opening the writer; wait until the held HTTP request arrives.
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            connection.request("GET", "/probe-ready")
            with connection.getresponse() as response:
                assert (response.status, response.read()) == (200, b"ready")

        assert (_probe_claim(lock_file), process.poll()) == (10, None)

        process.kill()
        process.communicate(timeout=PROCESS_TIMEOUT)
        if sys.platform == "win32":
            assert process.returncode not in (None, 0)
        else:
            assert process.returncode == -signal.SIGKILL

        assert _probe_claim(lock_file) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=PROCESS_TIMEOUT)


@pytest.mark.slow
def test_a_completed_crawl_releases_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))

    # This test process stays alive after the service returns, throughout the OS probe.
    result = crawl_result(server.url("/"))
    lock_file = result.crawl_file.with_name(f"{result.crawl_id}.lock")
    assert (result.summary.state, lock_file.is_file()) == ("completed", True)

    assert _probe_claim(lock_file) == 0


@pytest.mark.slow
def test_a_failed_creation_releases_its_writer_claim(temp_workspace: TempWorkspace) -> None:
    workspace = current_workspace(temp_workspace)
    crawl_file = workspace.crawls_dir / "20260927-140312-k3f9.sqlite"
    lock_file = crawl_file.with_suffix(".lock")
    before_schema: list[tuple[int, bool, int]] = []

    def observe_creation(connection: sqlite3.Connection, _: object) -> None:
        claim_code = _probe_claim(lock_file)
        (version,) = connection.execute("PRAGMA user_version").fetchone()
        before_schema.append((version, crawl_file.is_file(), claim_code))

    with disk_full_after(pages=1, include_creation=True):
        event.listen(Engine, "connect", observe_creation)
        try:
            with (
                pytest.raises(OpenLinxError) as raised,
                create_crawl(
                    new_crawl(workspace),
                    FakeClock(start=STARTED_AT),
                    Collected(),
                    scripted_choice("k3f9"),
                ),
            ):
                pass
        finally:
            event.remove(Engine, "connect", observe_creation)

    assert before_schema == [(0, True, 10)]
    assert (raised.value.code, raised.value.diagnostic.details) == (
        "workspace_not_writable",
        {"path": str(crawl_file), "error": "SQLITE_FULL"},
    )
    assert (crawl_file.exists(), lock_file.is_file()) == (False, True)

    assert _probe_claim(lock_file) == 0


@pytest.mark.slow
def test_creation_holds_its_writer_claim_before_writing_the_schema(
    temp_workspace: TempWorkspace,
) -> None:
    workspace = current_workspace(temp_workspace)
    crawl_file = workspace.crawls_dir / "20260927-140312-k3f9.sqlite"
    lock_file = crawl_file.with_suffix(".lock")
    before_schema: list[tuple[bool, list[tuple[object, ...]], int]] = []

    def before_create_table(
        _connection: object, _cursor: object, statement: str, *_: object
    ) -> None:
        if before_schema or not statement.lstrip().upper().startswith("CREATE TABLE "):
            return
        tables = query(crawl_file, "SELECT name FROM sqlite_schema WHERE type = 'table'")
        lock_exists = lock_file.is_file()
        # The first DDL cannot run until the other process has tried to take the claim.
        before_schema.append((lock_exists, tables, _probe_claim(lock_file)))

    event.listen(Engine, "before_cursor_execute", before_create_table)
    try:
        with create_crawl(
            new_crawl(workspace),
            FakeClock(start=STARTED_AT),
            Collected(),
            scripted_choice("k3f9"),
        ) as created:
            assert created.path == crawl_file
    finally:
        event.remove(Engine, "before_cursor_execute", before_create_table)

    assert before_schema == [(True, [], 10)]
    assert query(crawl_file, "SELECT id, state FROM crawl") == [("20260927-140312-k3f9", "running")]
    assert query(crawl_file, "SELECT position, url FROM seeds") == [(1, "https://example.com/")]


@pytest.mark.slow
def test_creation_holds_its_writer_claim_before_creating_the_sqlite_file(
    temp_workspace: TempWorkspace,
) -> None:
    # Audit hooks last for the life of the process, so scope the observer to a child.
    command = python_command(
        "-c",
        "import sys; from tests.crawl.test_claim import _observe_exclusive_create; "
        "_observe_exclusive_create(*sys.argv[1:])",
        str(temp_workspace.root),
        str(temp_workspace.home),
    )
    child = subprocess.run(
        command.argv,
        env=command.env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    assert child.returncode == 0, child.stderr.decode(errors="replace")


def _observe_exclusive_create(root: str, home: str) -> None:
    workspace = resolve_workspace(cwd=Path(root), flag=None, home=Path(home))
    crawl_file = workspace.crawls_dir / "20260927-140312-k3f9.sqlite"
    lock_file = crawl_file.with_suffix(".lock")
    claim_at_create: list[int | None] = []

    def on_open(event_name: str, args: tuple[object, ...]) -> None:
        if event_name == "open" and args[0] == str(crawl_file):
            flags = args[2]
            if isinstance(flags, int) and flags & os.O_EXCL:
                claim_at_create.append(_probe_claim(lock_file) if lock_file.is_file() else None)

    sys.addaudithook(on_open)
    with create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    ) as created:
        assert created.path == crawl_file
    assert claim_at_create == [10], claim_at_create


@pytest.mark.slow
@pytest.mark.parametrize(
    ("stop_reason", "error_code"),
    [("seed_unreachable", "seed_unreachable"), ("write_failed", "crawl_write_failed")],
    ids=["network_failure", "full_disk"],
)
def test_a_failed_crawl_releases_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite, stop_reason: str, error_code: str
) -> None:
    if stop_reason == "seed_unreachable":
        seed = f"http://127.0.0.1:{closed_port()}/"
    else:
        # The Page's title outgrows the capped writer; a fresh fallback writer records the end.
        title = "x" * 1_048_576
        server = fixture_site(Site(routes={"/": Page(body=f"<title>{title}</title>")}))
        seed = server.url("/")

    with disk_full_after(pages=8) if stop_reason == "write_failed" else nullcontext():
        result = crawl_result(seed, network_wait=0)

    failure = result.failure
    assert failure is not None
    lock_file = result.crawl_file.with_name(f"{result.crawl_id}.lock")
    assert (
        result.summary.state,
        result.summary.stop_reason,
        failure.code,
        query(result.crawl_file, "SELECT state, stop_reason FROM crawl"),
        lock_file.is_file(),
    ) == ("failed", stop_reason, error_code, [("failed", stop_reason)], True)
    if stop_reason == "write_failed":
        assert "database or disk is full" in failure.diagnostic.details["error"]

    assert _probe_claim(lock_file) == 0


@pytest.mark.slow
def test_post_crawl_passes_keep_the_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))
    crawls_dir = current_workspace(temp_workspace).crawls_dir
    attempts: list[int] = []

    async def check_claim(_context: PassContext) -> None:
        (crawl_file,) = crawls_dir.glob("*.sqlite")
        # The pass waits for the separate process to try the claim before the Crawl can finish.
        attempts.append(await asyncio.to_thread(_probe_claim, crawl_file.with_suffix(".lock")))

    result = crawl_result(server.url("/"), Hooks(passes=(Pass("claim", check_claim),)))

    assert (result.summary.state, attempts) == ("completed", [10])


@pytest.mark.slow
def test_failure_recording_keeps_the_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    title = "x" * 1_048_576
    server = fixture_site(Site(routes={"/": Page(body=f"<title>{title}</title>")}))
    crawls_dir = current_workspace(temp_workspace).crawls_dir
    failed_writer: object = None
    attempts: list[tuple[str, int]] = []

    def record_failure(context: ExceptionContext) -> None:
        nonlocal failed_writer
        if getattr(context.original_exception, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
            assert context.connection is not None
            failed_writer = context.connection.connection.driver_connection

    def probe_while_closing(connection: sqlite3.Connection, _: object) -> None:
        if connection is failed_writer:
            (crawl_file,) = crawls_dir.glob("*.sqlite")
            attempts.append(("primary closing", _probe_claim(crawl_file.with_suffix(".lock"))))

    def probe_while_opening(connection: sqlite3.Connection, _: object) -> None:
        if not attempts or attempts[-1][0] != "primary closing":
            return
        assert connection.execute("SELECT state FROM crawl").fetchone() == ("running",)
        (crawl_file,) = crawls_dir.glob("*.sqlite")
        attempts.append(("fallback opening", _probe_claim(crawl_file.with_suffix(".lock"))))

    with disk_full_after(pages=8):
        event.listen(Engine, "handle_error", record_failure)
        event.listen(Engine, "close", probe_while_closing)
        event.listen(Engine, "connect", probe_while_opening)
        try:
            result = crawl_result(server.url("/"))
        finally:
            event.remove(Engine, "connect", probe_while_opening)
            event.remove(Engine, "close", probe_while_closing)
            event.remove(Engine, "handle_error", record_failure)

    assert attempts == [("primary closing", 10), ("fallback opening", 10)]
    assert result.failure is not None
    assert (
        result.failure.code,
        query(result.crawl_file, "SELECT state, stop_reason FROM crawl"),
    ) == ("crawl_write_failed", [("failed", "write_failed")])


@pytest.mark.slow
@pytest.mark.parametrize(
    "via_symlink",
    [
        pytest.param(False, id="crawl_file"),
        pytest.param(True, id="file_symlink"),
    ],
)
def test_a_continuing_crawl_keeps_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path, via_symlink: bool
) -> None:
    during_request: list[int] = []
    before_read: list[int] = []
    during_writer_close: list[int] = []

    def resolve(path: str) -> Route | None:
        if path != "/next":
            return None
        during_request.append(_probe_claim(lock_file))
        return Page(body="<p>Next</p>")

    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/next">Next</a>')}, resolve=resolve)
    )
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert (stopped.summary.state, during_request) == ("stopped", [])
    lock_file = stopped.crawl_file.with_suffix(".lock")
    selected_path = stopped.crawl_file
    if via_symlink:
        alias = tmp_path / "alias.sqlite"
        try:
            alias.symlink_to(stopped.crawl_file)
        except OSError as error:
            if sys.platform == "win32" and getattr(error, "winerror", None) == 1314:
                pytest.skip("Windows denied file symlink creation (ERROR_PRIVILEGE_NOT_HELD)")
            raise
        selected_path = alias
    selected = resolve_crawl(
        str(selected_path), workspace=current_workspace(temp_workspace), cwd=tmp_path
    )
    assert (selected.id, selected.path) == (stopped.crawl_id, selected_path)

    def observe_first_connection(_connection: sqlite3.Connection, _: object) -> None:
        if not before_read:
            before_read.append(_probe_claim(lock_file))

    def observe_writer_close(connection: sqlite3.Connection, _: object) -> None:
        if connection.execute("SELECT state FROM crawl").fetchone() == ("completed",):
            during_writer_close.append(_probe_claim(lock_file))

    reporter = Collected()
    event.listen(Engine, "connect", observe_first_connection)
    event.listen(Engine, "close", observe_writer_close)
    try:
        result = continue_crawl(
            selected, CrawlOverrides(max_urls=3), SystemClock(), reporter, default_hooks()
        )
    finally:
        event.remove(Engine, "close", observe_writer_close)
        event.remove(Engine, "connect", observe_first_connection)

    assert (before_read, during_request, during_writer_close, _probe_claim(lock_file)) == (
        [10],
        [10],
        [10],
        0,
    )
    assert (result.summary.state, result.crawl_id, result.crawl_file) == (
        "completed",
        stopped.crawl_id,
        selected_path,
    )
    assert [data["crawl_file"] for name, data in reporter.events if name == "crawl_started"] == [
        str(selected_path)
    ]
    assert query(stopped.crawl_file, "SELECT url, fetch_state FROM urls ORDER BY id") == [
        (server.url("/"), "fetched"),
        (server.url("/next"), "fetched"),
    ]
    assert [request.path for request in server.requests] == [
        "/robots.txt",
        "/",
        "/robots.txt",
        "/next",
    ]


def test_continue_refuses_a_replaced_selection_even_with_the_same_crawl_id(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    selected = resolve_crawl(
        str(stopped.crawl_file), workspace=current_workspace(temp_workspace), cwd=tmp_path
    )
    original = selected.path.with_name("original.sqlite")
    selected.path.rename(original)
    copyfile(original, selected.path)
    assert not original.samefile(selected.path)

    reporter = Collected()
    with pytest.raises(OpenLinxError) as caught:
        continue_crawl(
            selected, CrawlOverrides(max_urls=3), SystemClock(), reporter, default_hooks()
        )

    assert (caught.value.code, caught.value.exit_code, dict(caught.value.diagnostic.details)) == (
        "crawl_not_writable",
        7,
        {"file": str(selected.path)},
    )
    assert re.search(
        r"\bcrawl file\b.*\b(?:has changed|is unavailable|is no longer available|was replaced)\b",
        caught.value.diagnostic.message,
        re.IGNORECASE,
    )
    for file in (original, selected.path):
        assert query(file, "SELECT id, state FROM crawl") == [(selected.id, "stopped")]
        assert query(file, "SELECT url, fetch_state, attempt_count FROM urls ORDER BY id") == [
            (server.url("/"), "fetched", 1),
            (server.url("/next"), "queued", 0),
        ]
    assert reporter.events == []
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


def test_continue_reports_a_selected_file_moved_during_open(
    temp_workspace: TempWorkspace, fixture_site: StartSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    selected = resolve_crawl(
        str(stopped.crawl_file),
        workspace=current_workspace(temp_workspace),
        cwd=temp_workspace.root,
    )
    moved = selected.path.with_name("moved.sqlite")
    original_connect = sqlite3.connect

    def connect(database: str, *, uri: bool, timeout: float) -> sqlite3.Connection:
        # Simulate the file being moved just as SQLite tries to open it.
        selected.path.rename(moved)
        return original_connect(database, uri=uri, timeout=timeout)

    reporter = Collected()
    with monkeypatch.context() as system:
        system.setattr(sqlite3, "connect", connect)
        with pytest.raises(OpenLinxError) as caught:
            continue_crawl(
                selected, CrawlOverrides(max_urls=3), SystemClock(), reporter, default_hooks()
            )

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "crawl_not_writable",
        7,
        {"file": str(selected.path)},
    )
    assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
    assert query(moved, "SELECT id, state FROM crawl") == [(selected.id, "stopped")]
    assert query(moved, "SELECT url, fetch_state, attempt_count FROM urls ORDER BY id") == [
        (server.url("/"), "fetched", 1),
        (server.url("/next"), "queued", 0),
    ]
    assert reporter.events == []
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


def test_continue_refuses_a_selected_symlink_that_becomes_a_loop(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    alias = tmp_path / "selected.sqlite"
    try:
        alias.symlink_to(stopped.crawl_file)
    except OSError as error:
        if sys.platform == "win32" and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows denied file symlink creation (ERROR_PRIVILEGE_NOT_HELD)")
        raise
    selected = resolve_crawl(str(alias), workspace=current_workspace(temp_workspace), cwd=tmp_path)
    assert (selected.id, selected.path) == (stopped.crawl_id, alias)
    alias.unlink()
    alias.symlink_to(alias.name)

    reporter = Collected()
    store_activity = 0

    def observe_store(*_: object) -> None:
        nonlocal store_activity
        store_activity += 1

    event.listen(Engine, "connect", observe_store)
    event.listen(Engine, "handle_error", observe_store)
    try:
        with pytest.raises(OpenLinxError) as caught:
            continue_crawl(
                selected, CrawlOverrides(max_urls=3), SystemClock(), reporter, default_hooks()
            )
    finally:
        event.remove(Engine, "handle_error", observe_store)
        event.remove(Engine, "connect", observe_store)

    assert (caught.value.code, caught.value.exit_code, dict(caught.value.diagnostic.details)) == (
        "crawl_not_writable",
        7,
        {"file": str(alias)},
    )
    assert re.search(_CLAIM_OPEN_FAILED, caught.value.diagnostic.message, re.IGNORECASE)
    assert (store_activity, reporter.events) == (0, [])
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


@pytest.mark.parametrize("use_alias", [False, True], ids=["original", "alias"])
def test_continue_refuses_a_crawl_with_hard_links_before_opening_it(
    temp_workspace: TempWorkspace, fixture_site: StartSite, use_alias: bool
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    alias = stopped.crawl_file.parent / "other" / "alias.sqlite"
    alias.parent.mkdir()
    alias.hardlink_to(stopped.crawl_file)
    assert alias.samefile(stopped.crawl_file)
    assert alias.resolve() != stopped.crawl_file.resolve()
    selected = replace(stopped, crawl_file=alias) if use_alias else stopped
    reporter = Collected()
    connections: list[sqlite3.Connection] = []

    def observe_connect(connection: sqlite3.Connection, _: object) -> None:
        connections.append(connection)

    event.listen(Engine, "connect", observe_connect)
    try:
        with pytest.raises(OpenLinxError) as caught:
            continued(selected, CrawlOverrides(max_urls=3), reporter=reporter)
    finally:
        event.remove(Engine, "connect", observe_connect)

    assert (caught.value.code, caught.value.exit_code, dict(caught.value.diagnostic.details)) == (
        "crawl_not_writable",
        7,
        {"file": str(selected.crawl_file)},
    )
    assert re.search(
        r"\b(?:multiple|more than one|several) hard links?\b",
        caught.value.diagnostic.message,
        re.IGNORECASE,
    )
    assert (connections, reporter.events) == ([], [])
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]
    assert list(alias.parent.iterdir()) == [alias]


type ClaimOperation = Literal["position", "acquire", "release"]


def _fail_claim_operation(
    system: pytest.MonkeyPatch, lock_file: Path, operation: ClaimOperation, failure: OSError
) -> None:
    if operation == "position":
        real_open = Path.open

        def seek(*args: object) -> int:
            raise failure

        def open_file(path: Path, *args: Any, **kwargs: Any) -> Any:
            handle = real_open(path, *args, **kwargs)
            if path == lock_file:
                system.setattr(handle, "seek", seek)
            return handle

        system.setattr(Path, "open", open_file)
    elif sys.platform == "win32":
        real_locking = msvcrt.locking
        failing_mode = msvcrt.LK_NBLCK if operation == "acquire" else msvcrt.LK_UNLCK

        def locking(fd: int, mode: int, nbytes: int) -> None:
            if mode == failing_mode:
                raise failure
            real_locking(fd, mode, nbytes)

        system.setattr(msvcrt, "locking", locking)
    else:
        real_flock = fcntl.flock
        failing_flags = fcntl.LOCK_EX | fcntl.LOCK_NB if operation == "acquire" else fcntl.LOCK_UN

        def flock(fd: int, flags: int) -> None:
            if flags == failing_flags:
                raise failure
            real_flock(fd, flags)

        system.setattr(fcntl, "flock", flock)


@pytest.mark.parametrize("operation", ["position", "acquire", "release"])
def test_continue_reports_a_writer_claim_system_failure(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    monkeypatch: pytest.MonkeyPatch,
    operation: ClaimOperation,
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"
    selected = resolve_crawl(
        str(stopped.crawl_file),
        workspace=current_workspace(temp_workspace),
        cwd=temp_workspace.root,
    )
    lock_file = selected.path.resolve().with_suffix(".lock")
    failure = OSError(errno.EIO, "I/O error in writer claim")

    with monkeypatch.context() as system:
        _fail_claim_operation(system, lock_file, operation, failure)
        with pytest.raises(OpenLinxError) as caught:
            continue_crawl(
                selected, CrawlOverrides(max_urls=3), SystemClock(), Collected(), default_hooks()
            )

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "crawl_not_writable",
        7,
        {"file": str(selected.path)},
    )
    assert caught.value.__cause__ is failure
    assert _probe_claim(lock_file) == 0
    if operation == "release":
        assert query(selected.path, "SELECT state FROM crawl") == [("completed",)]
        assert [request.path for request in server.requests] == [
            "/robots.txt",
            "/",
            "/robots.txt",
            "/next",
        ]
    else:
        assert query(selected.path, "SELECT state FROM crawl") == [("stopped",)]
        assert [request.path for request in server.requests] == ["/robots.txt", "/"]


def test_a_failed_claim_release_preserves_the_continue_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    selected = resolve_crawl(
        str(stopped.crawl_file),
        workspace=current_workspace(temp_workspace),
        cwd=temp_workspace.root,
    )
    lock_file = selected.path.resolve().with_suffix(".lock")
    reporter = Collected()

    with monkeypatch.context() as system:
        _fail_claim_operation(system, lock_file, "release", OSError(errno.EIO, "Cannot unlock"))
        with pytest.raises(OpenLinxError) as caught:
            continue_crawl(
                selected, CrawlOverrides(concurrency=0), SystemClock(), reporter, default_hooks()
            )

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "invalid_value",
        2,
        {"key": "crawl.concurrency"},
    )
    assert _probe_claim(lock_file) == 0
    assert query(selected.path, "SELECT state FROM crawl") == [("stopped",)]
    assert reporter.events == []
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


def test_continue_reports_an_unwritable_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), max_urls=1)
    assert stopped.summary.state == "stopped"

    with (
        read_only_file(stopped.crawl_file.with_suffix(".lock")),
        pytest.raises(OpenLinxError) as caught,
    ):
        continued(stopped, CrawlOverrides(max_urls=3))

    assert (caught.value.code, caught.value.exit_code, dict(caught.value.diagnostic.details)) == (
        "crawl_not_writable",
        7,
        {"file": str(stopped.crawl_file)},
    )
    assert re.search(_CLAIM_OPEN_FAILED, caught.value.diagnostic.message, re.IGNORECASE)
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]
