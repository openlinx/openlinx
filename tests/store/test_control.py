"""Exercise control requests and ordinary writer replay against real SQLite."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event, current_thread
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, event
from sqlalchemy.exc import DBAPIError

from openlinx.crawl.engine.stop import StopSignal
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.connections import is_busy, opening
from openlinx.store.records import CrawlFile
from openlinx.store.writer import CrawlWriter
from tests.support.cli import PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now

ADD_STOP = """
INSERT INTO control_requests (kind, requested_at, requested_by_pid)
VALUES ('stop', '2026-09-27T14:03:12Z', 123)
"""
KEEP = "INSERT INTO seeds VALUES (2, 'https://example.com/retained')"
ROLL_BACK = "INSERT INTO seeds VALUES (3, 'https://example.com/rolled-back')"


@pytest.fixture(params=["wal", "delete"])
def crawl_file(temp_workspace: TempWorkspace, request: pytest.FixtureRequest) -> CrawlFile:
    crawl = create_any_crawl(temp_workspace, journal_setting=request.param)
    assert query(crawl.path, "PRAGMA journal_mode") == [(request.param,)]
    return crawl


def test_stop_records_a_request_at_the_service_clock(
    crawl_file: CrawlFile, temp_workspace: TempWorkspace
) -> None:
    from openlinx.services.control import StopRequest, request_stop

    request = StopRequest(
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        crawl=crawl_file.id,
        wait_seconds=0,
    )
    clock = FakeClock(start=datetime.fromisoformat("2026-09-28T14:05:13.456Z"))

    result = request_stop(request, clock)

    assert (result.crawl_id, result.state, result.stop_reason, result.stop_requested) == (
        crawl_file.id,
        "running",
        None,
        True,
    )
    assert query(crawl_file.path, "SELECT kind, requested_at FROM control_requests") == [
        ("stop", "2026-09-28T14:05:13.456Z")
    ]
    assert clock.monotonic() == 0


@pytest.mark.parametrize(
    ("commit_at", "expected"),
    [
        pytest.param(2.0, ("stopped", "requested", False), id="before"),
        pytest.param(3.0, ("stopped", "requested", False), id="at"),
        pytest.param(3.25, ("running", None, True), id="after"),
    ],
)
def test_stop_wait_ignores_a_commit_after_its_deadline(
    crawl_file: CrawlFile,
    temp_workspace: TempWorkspace,
    commit_at: float,
    expected: tuple[str, str | None, bool],
) -> None:
    from openlinx.services.control import StopRequest, request_stop

    request = StopRequest(
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        crawl=crawl_file.id,
        wait_seconds=3,
    )

    with closing(sqlite3.connect(crawl_file.path)) as writer:

        class EndingClock(FakeClock):
            async def sleep(self, seconds: float) -> None:
                await super().sleep(seconds)
                if self.monotonic() == 3.0 and commit_at > 3.0:
                    # Model a callback that runs after its scheduled wake.
                    self.advance(commit_at - 3.0)
                if self.monotonic() == commit_at:
                    with writer:
                        writer.execute(
                            "UPDATE crawl SET state = 'stopped', stop_reason = 'requested'"
                        )

        clock = EndingClock()
        result = request_stop(request, clock)

    assert clock.monotonic() == commit_at
    assert query(crawl_file.path, "SELECT state, stop_reason FROM crawl") == [
        ("stopped", "requested")
    ]
    assert query(crawl_file.path, "SELECT kind FROM control_requests") == [("stop",)]
    assert result.crawl_id == crawl_file.id
    assert (result.state, result.stop_reason, result.stop_requested) == expected


@pytest.mark.parametrize("wait", [None, 3], ids=["default", "explicit"])
def test_stop_wait_expires_while_the_end_is_uncommitted(
    crawl_file: CrawlFile, temp_workspace: TempWorkspace, wait: int | None
) -> None:
    from openlinx.services.control import StopRequest, request_stop

    request = StopRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, workspace=None, crawl=crawl_file.id
    )
    if wait is not None:
        request = replace(request, wait_seconds=wait)

    with closing(sqlite3.connect(crawl_file.path, timeout=0)) as owner:

        class EndingClock(FakeClock):
            async def sleep(self, seconds: float) -> None:
                if not owner.in_transaction:
                    # Start the real terminal write after stop committed. WAL readers
                    # see the old state and a rollback-journal reader sees SQLITE_BUSY.
                    owner.execute("BEGIN EXCLUSIVE")
                    owner.execute("UPDATE crawl SET state = 'stopped', stop_reason = 'requested'")
                    self.shift_wall(-3600)
                await super().sleep(seconds)

        clock = EndingClock()
        result = request_stop(request, clock)

        assert owner.in_transaction
        assert clock.monotonic() == (60 if wait is None else 3)
        assert (result.crawl_id, result.state, result.stop_reason, result.stop_requested) == (
            crawl_file.id,
            "running",
            None,
            True,
        )
        owner.rollback()
    assert query(crawl_file.path, "SELECT state FROM crawl") == [("running",)]
    assert query(crawl_file.path, "SELECT kind, handled_at FROM control_requests") == [
        ("stop", None)
    ]


def test_stop_racing_with_completion_observes_the_committed_state(
    crawl_file: CrawlFile, temp_workspace: TempWorkspace
) -> None:
    from openlinx.services.control import StopRequest, request_stop
    from openlinx.store.crawls import set_state

    request = StopRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, workspace=None, crawl=crawl_file.id
    )
    owner_thread, acquiring = current_thread(), Event()
    clock = FakeClock()

    def before_sql(
        connection: Connection, cursor: Any, sql: str, params: Any, context: Any, many: bool
    ) -> None:
        if sql == "BEGIN IMMEDIATE" and current_thread() is not owner_thread:
            acquiring.set()

    event.listen(Engine, "before_cursor_execute", before_sql)
    try:
        with (
            ThreadPoolExecutor(max_workers=1) as executor,
            opening(crawl_file.path, role="write", identity=crawl_file.identity) as engine,
        ):
            with engine.begin() as writer:
                set_state(writer, "completed", clock.now())
                assert query(crawl_file.path, "SELECT state FROM crawl") == [("running",)]
                stop = executor.submit(request_stop, request, clock)
                # Hold the final commit until Stop has selected the Crawl and is at its write lock.
                assert acquiring.wait(PROCESS_TIMEOUT), "Stop did not reach its write transaction"
            result = stop.result(timeout=PROCESS_TIMEOUT)
    finally:
        event.remove(Engine, "before_cursor_execute", before_sql)

    assert (result.crawl_id, result.state, result.stop_reason, result.stop_requested) == (
        crawl_file.id,
        "completed",
        None,
        False,
    )
    assert query(crawl_file.path, "SELECT id FROM control_requests") == []


def test_control_reads_only_committed_rows(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import pending_stop_request

    with closing(sqlite3.connect(crawl_file.path)) as control:
        control.execute(ADD_STOP)
        assert pending_stop_request(crawl_file, after=0) is None
        control.rollback()
        assert pending_stop_request(crawl_file, after=0) is None
        control.execute(ADD_STOP)
        control.commit()
    assert pending_stop_request(crawl_file, after=0) == 1
    assert pending_stop_request(crawl_file, after=1) is None


def test_control_rejects_a_different_crawl_in_the_same_file(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import pending_stop_request, write_control

    assert crawl_file.identity is not None
    wrong = replace(crawl_file, id="20260928-140312-a1b2")
    with closing(sqlite3.connect(crawl_file.path)) as control, control:
        control.execute(ADD_STOP)
    with pytest.raises(OpenLinxError) as read:
        pending_stop_request(wrong, after=0)
    with pytest.raises(OpenLinxError) as write:
        write_control(wrong, FakeClock().now(), 123)
    for refused in (read.value, write.value):
        assert refused.code == "crawl_file_invalid"
        assert refused.diagnostic.details == {
            "file": str(crawl_file.path),
            "expected_id": wrong.id,
            "found_id": crawl_file.id,
        }
    assert query(crawl_file.path, "SELECT id FROM control_requests") == [(1,)]


def test_control_rejects_a_replacement_file_with_the_same_crawl_id(
    crawl_file: CrawlFile, temp_workspace: TempWorkspace
) -> None:
    from openlinx.store.control import pending_stop_request

    replacement = temp_workspace.root / "replacement.sqlite"
    with (
        closing(sqlite3.connect(crawl_file.path)) as original,
        closing(sqlite3.connect(replacement)) as restored,
    ):
        original.backup(restored)
        restored.execute(ADD_STOP)
        restored.commit()
        assert restored.execute("SELECT id FROM crawl").fetchone() == (crawl_file.id,)
    replacement.replace(crawl_file.path)
    with pytest.raises(OpenLinxError) as read:
        pending_stop_request(crawl_file, after=0)
    assert read.value.code == "crawl_not_writable"


def test_control_checks_again_on_the_next_tick_when_the_store_is_busy(
    crawl_file: CrawlFile,
) -> None:
    from openlinx.crawl.engine.heartbeat import watch_stop_requests
    from openlinx.store.control import pending_stop_request

    clock, stop = FakeClock(), StopSignal()
    with closing(sqlite3.connect(crawl_file.path, timeout=0)) as blocker:
        assert blocker.execute("PRAGMA locking_mode = EXCLUSIVE").fetchone() == ("exclusive",)
        blocker.execute("BEGIN EXCLUSIVE")
        blocker.execute(ADD_STOP)
        with pytest.raises(OpenLinxError, match="waited 0 seconds") as busy:
            pending_stop_request(crawl_file, after=0)
        assert busy.value.code == "crawl_busy"
        assert isinstance(busy.value.__cause__, DBAPIError)
        assert is_busy(busy.value.__cause__)

        async def release_after_first_tick() -> None:
            await clock.sleep(1.5)
            assert stop.is_set is False
            blocker.commit()
            blocker.close()

        async def drive() -> tuple[int, datetime] | None:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(release_after_first_tick())
                checking = tasks.create_task(watch_stop_requests(crawl_file, 0, clock, stop))
            return checking.result()

        assert asyncio.run(asyncio.wait_for(drive(), timeout=3)) == (
            1,
            datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        )
    assert (stop.reason, clock.monotonic()) == ("requested", 2)


def test_control_commit_during_replay_preserves_the_writer_batch(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import pending_stop_request, write_control

    clock = FakeClock()
    armed, committed = Event(), Event()
    writes: list[str] = []

    def keep(connection: Connection) -> str:
        connection.exec_driver_sql(KEEP)
        return "retained"

    def fail(connection: Connection) -> None:
        connection.exec_driver_sql(ROLL_BACK)
        raise ValueError("intentional unit failure")

    def before_sql(
        connection: Connection, cursor: Any, sql: str, params: Any, context: Any, many: bool
    ) -> None:
        if sql == KEEP:
            writes.append(sql)
        if sql == "BEGIN IMMEDIATE" and armed.is_set():
            # The writer has rolled back. Disarm before opening the control transaction.
            armed.clear()
            write_control(crawl_file, clock.now(), 123)
            committed.set()

    async def drive(writer: CrawlWriter) -> None:
        await writer.flush_async()
        assert await writer.run_async(keep) == "retained"
        assert pending_stop_request(crawl_file, after=0) is None
        armed.set()
        with pytest.raises(ValueError, match="intentional unit failure"):
            await writer.run_async(fail)
        assert committed.is_set()
        assert pending_stop_request(crawl_file, after=0) == 1
        await writer.flush_async()

    with CrawlWriter(crawl_file.path, clock, selected=crawl_file) as writer:
        event.listen(Engine, "before_cursor_execute", before_sql)
        try:
            asyncio.run(drive(writer))
        finally:
            event.remove(Engine, "before_cursor_execute", before_sql)
    assert writes == [KEEP, KEEP]
    assert query(crawl_file.path, "SELECT url FROM seeds ORDER BY position") == [
        ("https://example.com/",),
        ("https://example.com/retained",),
    ]


def test_handled_stop_keeps_its_id_and_time_during_writer_replay(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import pending_stop_request, record_stop_handled, write_control
    from openlinx.store.crawls import record_continue, record_state

    clock = FakeClock()
    with CrawlWriter(crawl_file.path, clock, selected=crawl_file) as writer:
        writer.run(record_state("stopped", clock.now(), "max_urls"))
        writer.flush()
        assert writer.run(record_continue({}, clock.now(), run_pid=789)) == 2
        replay_now(writer)
    assert query(crawl_file.path, "SELECT id, pid FROM crawl_runs WHERE id > 1") == [(2, 789)]
    write_control(crawl_file, clock.now(), 123)
    between_attempts = Event()
    rows = (
        "SELECT id, requested_by_pid, handled_at, handled_by_run_id "
        "FROM control_requests ORDER BY id"
    )

    def before_sql(
        connection: Connection, cursor: Any, sql: str, params: Any, context: Any, many: bool
    ) -> None:
        if sql == "BEGIN IMMEDIATE" and between_attempts.is_set():
            between_attempts.clear()
            write_control(crawl_file, clock.now(), 456)

    with CrawlWriter(crawl_file.path, clock, selected=crawl_file) as writer:
        event.listen(Engine, "before_cursor_execute", before_sql)
        try:
            writer.flush()
            writer.run(record_stop_handled(1, clock.now(), run_id=2))
            assert query(crawl_file.path, rows) == [(1, 123, None, None)]
            clock.shift_wall(3)
            between_attempts.set()
            replay_now(writer)
            assert pending_stop_request(crawl_file, after=0) == 2
            writer.run(record_stop_handled(1, clock.now(), run_id=1))
        finally:
            event.remove(Engine, "before_cursor_execute", before_sql)

    assert query(crawl_file.path, rows) == [
        (1, 123, "2026-01-01T00:00:00.000Z", 2),
        (2, 456, None, None),
    ]


def test_stop_request_during_grace_is_left_unhandled(crawl_file: CrawlFile) -> None:
    from openlinx.crawl.engine.heartbeat import watch_stop_requests
    from openlinx.store.control import write_control

    clock, stop = FakeClock(), StopSignal()
    write_control(crawl_file, clock.now(), 123)

    async def drive() -> None:
        stop.set("interrupt")
        assert await watch_stop_requests(crawl_file, 0, clock, stop) is None

    asyncio.run(asyncio.wait_for(drive(), timeout=3))
    assert stop.reason == "interrupt"
    assert query(crawl_file.path, "SELECT kind, handled_at FROM control_requests") == [
        ("stop", None)
    ]


def test_stop_refuses_a_read_only_crawl_file(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import write_control

    path = crawl_file.path
    with read_only_file(path):
        with pytest.raises(OpenLinxError) as refused:
            write_control(crawl_file, FakeClock().now(), 123)
        cause = refused.value.__cause__
        assert isinstance(cause, DBAPIError)
        assert isinstance(cause.orig, sqlite3.Error)
        assert cause.orig.sqlite_errorcode & 0xFF == sqlite3.SQLITE_READONLY
        reply = run_cli_process("stop", "--crawl", crawl_file.id)

    assert query(path, "SELECT state FROM crawl") == [("running",)]
    assert query(path, "SELECT id FROM control_requests") == []
    [failure] = reply.errors()
    assert (reply.exit_code, failure["code"], failure["details"].get("file")) == (
        7,
        "crawl_not_writable",
        str(path),
    )


@pytest.mark.parametrize("use_alias", [False, True], ids=["original", "alias"])
def test_stop_refuses_hard_links_before_opening_for_write(
    crawl_file: CrawlFile, use_alias: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = crawl_file.path
    alias = path.with_name("alias.sqlite")
    alias.hardlink_to(path)
    selected = alias if use_alias else path
    assert alias.samefile(path)
    assert path.stat().st_nlink == 2
    connect = sqlite3.connect
    writable_opens: list[str] = []

    def observe_connect(database: str, *, uri: bool, timeout: float) -> sqlite3.Connection:
        if database.endswith("?mode=rw"):
            writable_opens.append(database)
        return connect(database, uri=uri, timeout=timeout)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", observe_connect)
        result = run_cli("stop", "--wait", "0", "--crawl", str(selected))

    assert result.exit_code == 7, (result.stdout, result.stderr, writable_opens)
    [failure] = result.errors()
    assert (failure["code"], failure["details"], writable_opens) == (
        "crawl_not_writable",
        {"file": str(selected)},
        [],
    )
    assert query(path, "SELECT id FROM control_requests") == []


def test_a_control_write_cannot_change_other_tables(crawl_file: CrawlFile) -> None:
    with opening(crawl_file.path, role="control", busy_seconds=0) as engine, engine.begin() as db:
        db.exec_driver_sql(ADD_STOP)
        with pytest.raises(DBAPIError, match="not authorized"):
            db.exec_driver_sql("UPDATE crawl SET state = 'stopped'")
    assert query(crawl_file.path, "SELECT state FROM crawl") == [("running",)]
    assert query(crawl_file.path, "SELECT kind FROM control_requests") == [("stop",)]


def test_write_control_cannot_change_crawl_state_through_a_trigger(crawl_file: CrawlFile) -> None:
    from openlinx.store.control import write_control

    with closing(sqlite3.connect(crawl_file.path)) as db, db:
        db.execute("""
            CREATE TRIGGER change_crawl_state AFTER INSERT ON control_requests BEGIN
                UPDATE crawl SET state = 'stopped';
            END
        """)

    with pytest.raises(DBAPIError) as refused:
        write_control(crawl_file, FakeClock().now(), 123)

    assert isinstance(refused.value.orig, sqlite3.Error)
    assert refused.value.orig.sqlite_errorcode == sqlite3.SQLITE_AUTH
    assert query(crawl_file.path, "SELECT state FROM crawl") == [("running",)]
    assert query(crawl_file.path, "SELECT kind FROM control_requests") == []
