"""Drive Crawl control through real Commands sharing a crawl file."""

import asyncio
import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import Connection, Engine, event

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.crawl.engine.stop import StopSignal
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides
from openlinx.services.hooks import default_hooks
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site
from tests.support.cli import (
    CLI_PROCESS_TIMEOUT,
    CRAWL_PROCESS_TIMEOUT,
    PROCESS_TIMEOUT,
    await_event,
    run_cli_process,
    start_cli_process,
)
from tests.support.clock import FakeClock
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace


def _get(connection: HTTPConnection, path: str) -> bytes:
    connection.request("GET", path)
    with connection.getresponse() as response:
        assert response.status == 200
        return response.read()


@pytest.fixture
def held_foreground_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> Iterator[tuple[subprocess.Popen[bytes], str, Path, HTTPConnection]]:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/held">Held</a>'),
                "/held": Page(body="<p>Held Page</p>", after="/release"),
                "/ready": Page(body="ready", after="/held"),
                "/release": Page(body="released"),
            }
        )
    )
    owner = start_cli_process("crawl", server.url("/"), "--concurrency", "1")
    try:
        started = await_event(owner, "crawl_started")
        crawl_id, crawl_file = started["crawl_id"], Path(started["crawl_file"])
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            assert _get(connection, "/ready") == b"ready"
            assert query(crawl_file, "SELECT state FROM crawl") == [("running",)]
            yield owner, crawl_id, crawl_file, connection
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=PROCESS_TIMEOUT)


@pytest.fixture
def stopped_foreground_crawl(
    held_foreground_crawl: tuple[subprocess.Popen[bytes], str, Path, HTTPConnection],
) -> tuple[Path, int]:
    owner, crawl_id, crawl_file, connection = held_foreground_crawl
    with start_cli_process("stop", "--crawl", crawl_id, "--wait", "0") as requester:
        try:
            _, diagnostic = requester.communicate(timeout=CLI_PROCESS_TIMEOUT)
            assert requester.returncode == 0, diagnostic.decode(errors="replace")
        finally:
            if requester.poll() is None:
                requester.kill()
                requester.communicate(timeout=PROCESS_TIMEOUT)
    try:
        assert await_event(owner, "stopping") == {"crawl_id": crawl_id, "reason": "requested"}
    finally:
        assert _get(connection, "/release") == b"released"
    stdout, stderr = owner.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
    assert owner.returncode == 0, stderr.decode(errors="replace")
    result = json.loads(stdout)
    assert (result["crawl_id"], result["state"], result["stop_reason"]) == (
        crawl_id,
        "stopped",
        "requested",
    )
    return crawl_file, requester.pid


@pytest.mark.slow
def test_a_stop_request_is_recorded_as_handled(stopped_foreground_crawl: tuple[Path, int]) -> None:
    crawl_file, _ = stopped_foreground_crawl
    [(kind, handled_at)] = query(crawl_file, "SELECT kind, handled_at FROM control_requests")
    assert kind == "stop"
    assert handled_at is not None


@pytest.mark.slow
def test_a_stop_request_names_who_wrote_it_and_which_run_handled_it(
    stopped_foreground_crawl: tuple[Path, int],
) -> None:
    crawl_file, requester_pid = stopped_foreground_crawl
    requests = query(crawl_file, "SELECT requested_by_pid, handled_by_run_id FROM control_requests")
    assert requests == [(requester_pid, 1)]


@pytest.mark.slow
def test_stop_waits_for_the_crawl_to_stop(
    held_foreground_crawl: tuple[subprocess.Popen[bytes], str, Path, HTTPConnection],
) -> None:
    owner, crawl_id, crawl_file, connection = held_foreground_crawl
    requester = start_cli_process("stop", "--crawl", crawl_id)
    try:
        try:
            assert await_event(owner, "stopping") == {"crawl_id": crawl_id, "reason": "requested"}
            assert query(crawl_file, "SELECT state FROM crawl") == [("running",)]
        finally:
            assert _get(connection, "/release") == b"released"
        reply, diagnostic = requester.communicate(timeout=CLI_PROCESS_TIMEOUT)
        assert requester.returncode == 0, diagnostic.decode(errors="replace")
    finally:
        if requester.poll() is None:
            requester.kill()
        requester.communicate(timeout=PROCESS_TIMEOUT)

    assert json.loads(reply) == {
        "crawl_id": crawl_id,
        "state": "stopped",
        "stop_reason": "requested",
        "stop_requested": False,
    }
    stdout, stderr = owner.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
    assert owner.returncode == 0, stderr.decode(errors="replace")
    result = json.loads(stdout)
    assert (result["state"], result["stop_reason"]) == ("stopped", "requested")
    assert query(crawl_file, "SELECT state, stop_reason FROM crawl") == [("stopped", "requested")]


@pytest.mark.slow
def test_stop_can_return_at_once(
    held_foreground_crawl: tuple[subprocess.Popen[bytes], str, Path, HTTPConnection],
) -> None:
    owner, crawl_id, crawl_file, connection = held_foreground_crawl
    try:
        reply = run_cli_process("stop", "--crawl", crawl_id, "--wait", "0")
        assert reply.exit_code == 0, reply.stderr.decode(errors="replace")
        assert reply.json() == {
            "crawl_id": crawl_id,
            "state": "running",
            "stop_reason": None,
            "stop_requested": True,
        }
        assert query(crawl_file, "SELECT kind FROM control_requests") == [("stop",)]
        assert query(crawl_file, "SELECT state FROM crawl") == [("running",)]
        assert await_event(owner, "stopping") == {"crawl_id": crawl_id, "reason": "requested"}
    finally:
        assert _get(connection, "/release") == b"released"

    stdout, stderr = owner.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
    assert owner.returncode == 0, stderr.decode(errors="replace")
    result = json.loads(stdout)
    assert (result["state"], result["stop_reason"]) == ("stopped", "requested")
    assert query(crawl_file, "SELECT state, stop_reason FROM crawl") == [("stopped", "requested")]


@pytest.mark.slow
def test_a_request_that_outlasts_the_grace_period_stays_queued(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/hang">Hang</a><a href="/quick">Quick</a>'),
                "/hang": Page(body="<p>Late Page</p>", delay=60),
                "/quick": Page(body="<title>Quick Page</title>", after="/release-quick"),
                "/ready-hang": Page(body="hang ready", after="/hang"),
                "/ready-quick": Page(body="quick ready", after="/quick"),
                "/release-quick": Page(body="released"),
            }
        )
    )
    owner = start_cli_process("crawl", server.url("/"), "--concurrency", "2", "--timeout", "75")
    try:
        started = await_event(owner, "crawl_started")
        crawl_id, crawl_file = started["crawl_id"], Path(started["crawl_file"])
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            assert _get(connection, "/ready-hang") == b"hang ready"
            assert _get(connection, "/ready-quick") == b"quick ready"
            requester = start_cli_process("stop", "--crawl", crawl_id)
            try:
                try:
                    assert await_event(owner, "stopping") == {
                        "crawl_id": crawl_id,
                        "reason": "requested",
                    }
                finally:
                    assert _get(connection, "/release-quick") == b"released"
                reply, diagnostic = requester.communicate(timeout=CLI_PROCESS_TIMEOUT)
                assert requester.returncode == 0, diagnostic.decode(errors="replace")
            finally:
                if requester.poll() is None:
                    requester.kill()
                requester.communicate(timeout=PROCESS_TIMEOUT)

        stdout, stderr = owner.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
        assert owner.returncode == 0, stderr.decode(errors="replace")
        for result in (json.loads(reply), json.loads(stdout)):
            assert (result["crawl_id"], result["state"], result["stop_reason"]) == (
                crawl_id,
                "stopped",
                "requested",
            )
        assert query(
            crawl_file,
            "SELECT url, fetch_state, pages.url_id IS NOT NULL, pages.title_1 "
            "FROM urls LEFT JOIN pages ON urls.id = pages.url_id "
            "WHERE url IN (?, ?) ORDER BY url",
            [server.url("/hang"), server.url("/quick")],
        ) == [
            (server.url("/hang"), "queued", 0, None),
            (server.url("/quick"), "fetched", 1, "Quick Page"),
        ]
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=PROCESS_TIMEOUT)


@pytest.mark.slow
def test_a_crawl_waiting_for_the_network_stops_at_once(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    failed = [f"/offline-{number}" for number in range(1, 9)]
    links = "".join(f'<a href="{path}">Offline</a>' for path in failed)
    server = fixture_site(
        Site(
            routes={
                "/": Responses((Page(body=links), Page(body="", hang=True))),
                **{path: Page(body="", reset_before_headers=True) for path in failed},
            }
        )
    )
    owner = start_cli_process(
        "crawl", server.url("/"), "--concurrency", "1", "--retries", "0", "--network-wait", "120"
    )
    try:
        started = await_event(owner, "crawl_started")
        crawl_id, crawl_file = started["crawl_id"], Path(started["crawl_file"])
        paused = await_event(owner, "crawl_paused")
        assert paused["crawl_id"] == crawl_id
        assert paused["urls"] == [server.url(path) for path in failed]

        result = run_cli_process("stop", "--crawl", crawl_id, timeout=15)
        assert result.exit_code == 0, result.stderr
        assert result.json() == {
            "crawl_id": crawl_id,
            "state": "stopped",
            "stop_reason": "requested",
            "stop_requested": False,
        }
        stdout, stderr = owner.communicate(timeout=PROCESS_TIMEOUT)
        assert owner.returncode == 0, stderr.decode(errors="replace")
        finished = json.loads(stdout)
        assert (finished["crawl_id"], finished["state"], finished["stop_reason"]) == (
            crawl_id,
            "stopped",
            "requested",
        )
        assert query(crawl_file, "SELECT state, stop_reason FROM crawl") == [
            ("stopped", "requested")
        ]
        assert query(
            crawl_file, "SELECT fetch_state, count(*) FROM urls GROUP BY fetch_state ORDER BY 1"
        ) == [("error", 8), ("fetched", 1)]
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=PROCESS_TIMEOUT)


@pytest.mark.slow
def test_a_foreground_crawl_in_another_terminal_is_stopped(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    paths = [f"/p{number}" for number in range(2, 61)]
    links = "".join(f'<a href="{path}">Page</a>' for path in paths)
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/p1">In flight</a>' + links),
                "/p1": Page(body="<p>In flight</p>", after="/release-p1"),
                "/probe-ready": Page(body="ready", after="/p1"),
                "/release-p1": Page(body="released"),
                **{path: Page(body="<p>Slow Page</p>", delay=1) for path in paths},
            }
        )
    )

    owner = start_cli_process(
        "crawl", server.url("/"), "--concurrency", "1", "--header", "X-Token: abc123"
    )
    try:
        started = await_event(owner, "crawl_started")
        crawl_id, crawl_file = started["crawl_id"], Path(started["crawl_file"])
        # Hold one response while the writer finishes its ordinary batch. Release
        # it only once the Crawl has seen the committed request and started its grace.
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            connection.request("GET", "/probe-ready")
            with connection.getresponse() as response:
                assert (response.status, response.read()) == (200, b"ready")
            assert owner.poll() is None
            assert query(crawl_file, "SELECT state FROM crawl") == [("running",)]

            [(run, started_at, argv, detached, owner_pid)] = query(
                crawl_file, "SELECT id, started_at, command_argv, detached, pid FROM crawl_runs"
            )

            try:
                with start_cli_process("stop", "--crawl", crawl_id, "--wait", "0") as requester:
                    try:
                        reply, diagnostic = requester.communicate(timeout=CLI_PROCESS_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        requester.kill()
                        requester.communicate()
                        raise
                    assert requester.returncode == 0, diagnostic.decode(errors="replace")
                assert await_event(owner, "stopping") == {
                    "crawl_id": crawl_id,
                    "reason": "requested",
                }
            finally:
                connection.request("GET", "/release-p1")
                with connection.getresponse() as response:
                    assert (response.status, response.read()) == (200, b"released")
        assert json.loads(reply) == {
            "crawl_id": crawl_id,
            "state": "running",
            "stop_reason": None,
            "stop_requested": True,
        }
        stdout, stderr = owner.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
        assert owner.returncode == 0, stderr.decode(errors="replace")
        result = json.loads(stdout)
        assert (result["crawl_id"], result["state"], result["stop_reason"]) == (
            crawl_id,
            "stopped",
            "requested",
        )
        assert query(crawl_file, "SELECT state, stop_reason FROM crawl") == [
            ("stopped", "requested")
        ]
        [(kind, at, pid, handled_at)] = query(
            crawl_file,
            "SELECT kind, requested_at, requested_by_pid, handled_at FROM control_requests",
        )
        assert kind == "stop"
        assert at.endswith("Z")
        assert handled_at is not None
        assert handled_at.endswith("Z")
        assert (
            datetime.fromisoformat(at)
            <= datetime.fromisoformat(handled_at)
            <= datetime.fromisoformat(result["ended_at"])
        )
        assert pid == requester.pid
        assert requester.pid != owner.pid
        assert (run, started_at, detached, owner_pid) == (1, result["started_at"], 0, owner.pid)
        assert json.loads(argv) == [
            "linx",
            "crawl",
            server.url("/"),
            "--concurrency",
            "1",
            "--header",
            "X-Token: ***",
        ]
        assert query(crawl_file, "SELECT handled_by_run_id FROM control_requests") == [(1,)]
        assert query(crawl_file, "SELECT count(*) FROM urls WHERE fetch_state = 'queued'") == [
            (59,)
        ]
        assert [hit.path for hit in server.requests if hit.path in ["/p1", *paths]] == ["/p1"]
        assert query(
            crawl_file,
            "SELECT count(*) FROM pages WHERE url_id IN (SELECT id FROM urls WHERE url = ?)",
            [server.url("/p1")],
        ) == [(1,)]
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=PROCESS_TIMEOUT)


@pytest.mark.parametrize("journal", ["wal", "delete"])
@pytest.mark.parametrize("phase", ["post-pass", "before-terminal-lock"])
def test_a_committed_stop_is_honoured_at_the_end(
    temp_workspace: TempWorkspace, journal: str, phase: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal}"\n', encoding="utf-8"
    )
    clock, reporter = FakeClock(), Collected()
    fetcher = FakeFetcher(clock, {"/": FakePage("<p>One Page</p>")})
    armed = Event()
    stopping, stop = asyncio.Event(), StopSignal()
    stop.on_first_set(lambda _: stopping.set())

    def commit_stop(requests: int) -> None:
        [started] = [data for name, data in reporter.events if name == "crawl_started"]
        file = Path(started["crawl_file"])
        assert query(file, "PRAGMA journal_mode") == [(journal,)]
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert query(file, "SELECT count(*) FROM pages") == [(1,)]
        reply = run_cli_process("stop", "--crawl", started["crawl_id"], "--wait", "0")
        assert reply.exit_code == 0, reply.stderr.decode(errors="replace")
        assert reply.json() == {
            "crawl_id": started["crawl_id"],
            "state": "running",
            "stop_reason": None,
            "stop_requested": True,
        }
        assert query(file, "SELECT id, kind FROM control_requests ORDER BY id") == [
            (number, "stop") for number in range(1, requests + 1)
        ]

    def before_sql(
        connection: Connection, cursor: Any, sql: str, params: Any, context: Any, many: bool
    ) -> None:
        if sql == "BEGIN IMMEDIATE" and armed.is_set():
            # The final writer transaction has started in SQLAlchemy, but SQLite has
            # yet to take its write lock. Let the second process acquire it first.
            armed.clear()
            commit_stop(1)
            commit_stop(2)
            # The owner may have started finalization before the request was accepted.
            clock.shift_wall(7)
            assert not stopping.is_set()

    async def hold_pass(context: PassContext) -> None:
        await context.writer.flush_async()
        if phase == "post-pass":
            with clock.off_loop():
                await asyncio.to_thread(commit_stop, 1)
            await asyncio.wait_for(stopping.wait(), timeout=PROCESS_TIMEOUT)
            await context.writer.flush_async()
            with clock.off_loop():
                await asyncio.to_thread(commit_stop, 2)
            clock.shift_wall(7)
        else:
            armed.set()

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("stop-boundary", hold_pass)))
    event.listen(Engine, "before_cursor_execute", before_sql)
    try:
        owner = crawl_result(
            "http://127.0.0.1/", hooks, clock=clock, reporter=reporter, fetcher=fetcher, stop=stop
        )
    finally:
        event.remove(Engine, "before_cursor_execute", before_sql)
    [(first_id, first_at, first_run), (second_id, second_at, second_run)] = query(
        owner.crawl_file,
        "SELECT id, handled_at, handled_by_run_id FROM control_requests ORDER BY id",
    )
    assert (first_id, first_run, second_id, second_at, second_run) == (1, 1, 2, None, None)
    if phase == "post-pass":
        assert first_at == "2026-01-01T00:00:01.000Z"
    else:
        assert first_at == "2026-01-01T00:00:07.000Z"
        assert owner.to_json()["ended_at"] == "2026-01-01T00:00:07.000Z"
    assert query(owner.crawl_file, "SELECT state, stop_reason FROM crawl") == [
        ("stopped", "requested")
    ]
    assert (owner.summary.state, owner.summary.stop_reason, owner.failure) == (
        "stopped",
        "requested",
        None,
    )
    assert [data for name, data in reporter.events if name == "stopping"] == [
        {"crawl_id": owner.crawl_id, "reason": "requested"}
    ]


@pytest.mark.parametrize("old_file", [False, True], ids=["old-stop-request", "before-control"])
def test_continuing_a_crawl_preserves_the_next_run(
    temp_workspace: TempWorkspace, old_file: bool
) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(
        clock, {"/": FakePage('<a href="/next">Next</a>'), "/next": FakePage("Next", delay=3)}
    )
    stopped = crawl_result("http://127.0.0.1/", clock=clock, fetcher=fetcher, max_urls=1)
    with closing(sqlite3.connect(stopped.crawl_file)) as db, db:
        if old_file:
            db.execute("DROP TABLE control_requests")
            db.execute("DROP TABLE crawl_runs")
        else:
            db.execute(
                "INSERT INTO control_requests (kind, requested_at, requested_by_pid) "
                "VALUES ('stop', '2026-09-27T14:03:12Z', 123)"
            )

    result = continued(stopped, CrawlOverrides(max_urls=None), clock=clock, fetcher=fetcher)

    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT count(*) FROM pages") == [(2,)]
    if not old_file:
        assert query(result.crawl_file, "SELECT id, handled_at FROM control_requests") == [
            (1, None)
        ]


def test_a_new_stop_names_the_continued_run(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(
        clock, {"/": FakePage('<a href="/next">Next</a>'), "/next": FakePage("Next")}
    )
    first = crawl_result("http://127.0.0.1/", clock=clock, fetcher=fetcher, max_urls=1)
    stopping, stop = asyncio.Event(), StopSignal()
    stop.on_first_set(lambda _: stopping.set())
    requester: subprocess.Popen[bytes] | None = None

    async def stop_after_the_pass(context: PassContext) -> None:
        nonlocal requester
        await context.writer.flush_async()
        requester = start_cli_process("stop", "--crawl", first.crawl_id, "--wait", "30")
        await asyncio.wait_for(stopping.wait(), timeout=PROCESS_TIMEOUT)
        assert query(first.crawl_file, "SELECT state FROM crawl") == [("running",)]

    hooks = default_hooks()
    hooks = replace(hooks, passes=(*hooks.passes, Pass("stop-continued-run", stop_after_the_pass)))
    try:
        second = continued(
            first, CrawlOverrides(max_urls=None), hooks, clock=clock, fetcher=fetcher, stop=stop
        )
        assert requester is not None
        reply, diagnostic = requester.communicate(timeout=CLI_PROCESS_TIMEOUT)
        assert requester.returncode == 0, diagnostic.decode(errors="replace")
        assert json.loads(reply) == {
            "crawl_id": first.crawl_id,
            "state": "stopped",
            "stop_reason": "requested",
            "stop_requested": False,
        }
    finally:
        if requester is not None:
            if requester.poll() is None:
                requester.kill()
            requester.communicate(timeout=PROCESS_TIMEOUT)

    assert (second.summary.state, second.summary.stop_reason) == ("stopped", "requested")
    assert query(first.crawl_file, "SELECT id, detached FROM crawl_runs ORDER BY id") == [
        (1, 0),
        (2, 0),
    ]
    assert query(first.crawl_file, "SELECT handled_by_run_id FROM control_requests") == [(2,)]
