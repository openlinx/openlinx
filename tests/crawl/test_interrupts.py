"""Stopping a Crawl with an interrupt (020-add-crawl-core D10, D16)."""

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from spider.crawl.engine.stop import StopSignal
from spider.output.reporter import Collected
from spider.services.crawling import CrawlResult
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.server import ServerHandle
from tests.support.cli import start_cli_process
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

# Each Page answers this slowly, so the Crawl is still running when the test interrupts it.
PAGE_DELAY = 0.3
# The default requests in flight to one host.
CONCURRENCY = 5

THIRTY_PAGES = Site(
    routes={
        "/": Page(body="".join(f'<a href="/p{n}">{n}</a>' for n in range(1, 30))),
        **{f"/p{n}": Page(body=f"<p>{n}</p>", delay=PAGE_DELAY) for n in range(1, 30)},
    }
)


def _await_fetched(server: ServerHandle, count: int) -> None:
    """Once `count` Pages have answered: a host takes a request only when one of its
    CONCURRENCY in flight has ended."""
    deadline = time.monotonic() + 20
    while sum(r.path.startswith("/p") for r in server.requests) < count + CONCURRENCY:
        assert time.monotonic() < deadline, "the Crawl never requested the pages"
        time.sleep(0.05)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("signum", ["SIGINT", "SIGTERM", "SIGHUP"])
def test_ctrl_c_stops_a_crawl_on_macos_and_linux(
    signum: str, temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(THIRTY_PAGES)
    process = start_cli_process("crawl", server.url("/"))
    _await_fetched(server, 3)

    process.send_signal(getattr(signal, signum))

    assert _how_it_ended(process) == (130, "stopped", "interrupt", ["interrupt"])


@pytest.mark.skipif(sys.platform != "win32", reason="Ctrl+Break is a Windows console event")
def test_ctrl_break_stops_a_crawl_on_windows(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(THIRTY_PAGES)
    # Started in its own process group, which alone gets the event.
    process = start_cli_process("crawl", server.url("/"))
    _await_fetched(server, 3)

    # The skip's condition again, which mypy reads only from an if.
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)

    assert _how_it_ended(process) == (130, "stopped", "interrupt", ["interrupt"])


def test_an_interrupt_is_reported_by_one_error(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(THIRTY_PAGES)
    process = start_cli_process("crawl", server.url("/"))
    _await_fetched(server, 3)

    _interrupt(process)
    stdout, stderr = process.communicate(timeout=30)

    lines = [json.loads(line) for line in stderr.splitlines()]
    errors = [line for line in lines if line.get("level") == "error"]
    resume = f"spider resume --crawl {json.loads(stdout)['crawl_id']}"
    # An agent is told how to go on, as every other early end of a Crawl tells it.
    assert (
        process.returncode,
        [error["code"] for error in errors],
        errors[-1:] == lines[-1:],
        [resume in (error["hint"] or "") for error in errors],
    ) == (130, ["interrupted"], True, [True])


def test_an_interrupted_crawl_keeps_its_queue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(THIRTY_PAGES)
    process = start_cli_process("crawl", server.url("/"))
    _await_fetched(server, 3)

    _interrupt(process)
    stdout, _ = process.communicate(timeout=30)

    crawl_file = Path(json.loads(stdout)["crawl_file"])
    assert query(crawl_file, "SELECT count(*) > 0 FROM urls WHERE fetch_state = 'queued'") == [(1,)]


_DOWN = range(1, 21)
# / links to /down/1 to /down/20, each of which sends its headers and then resets the
# connection: the Crawl pauses after the eighth at --concurrency 1.
LOST_SECTION = Site(
    routes={
        "/": Page(body="".join(f'<a href="/down/{n}">Down {n}</a>' for n in _DOWN)),
        **{f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in _DOWN},
    }
)


def test_a_stop_ends_a_pause(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(LOST_SECTION)
    process = start_cli_process(
        "crawl", server.url("/"), "--concurrency", "1", "--network-wait", "1800"
    )
    _await_event(process, "crawl_paused")

    interrupted_at = time.monotonic()
    _interrupt(process)
    stdout, stderr = process.communicate(timeout=30)

    result = json.loads(stdout)
    events = [json.loads(line).get("event") for line in stderr.splitlines()]
    # The probes request the Seed; the first is due 5 seconds into the pause.
    probes = [r for r in server.requests if r.path == "/" and r.received_at > interrupted_at]
    assert (
        process.returncode,
        result["state"],
        result["stop_reason"],
        events.count("stopping"),
        events.count("crawl_resumed"),
        probes,
    ) == (130, "stopped", "interrupt", 1, 0, [])


def _await_event(process: subprocess.Popen[bytes], name: str) -> None:
    assert process.stderr is not None
    for line in process.stderr:
        if json.loads(line).get("event") == name:
            return
    raise AssertionError(f"the Command ended without a {name} event")


def _interrupt(process: subprocess.Popen[bytes]) -> None:
    """Ctrl+C, or on Windows Ctrl+Break, which a process group alone gets."""
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGINT)


def _how_it_ended(process: subprocess.Popen[bytes]) -> tuple[int, str, str, list[str]]:
    stdout, stderr = process.communicate(timeout=30)
    result = json.loads(stdout)
    events = [json.loads(line) for line in stderr.splitlines()]
    stopping = [e["data"]["reason"] for e in events if e.get("event") == "stopping"]
    return process.returncode, result["state"], result["stop_reason"], stopping


def test_a_stop_that_ends_a_depth_reads_no_deeper_one(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    stop = StopSignal()
    reporter = Collected()
    pages = {
        "/": FakePage('<a href="http://other.test/slow">S</a><a href="/a">A</a>'),
        "http://other.test/slow": FakePage("<p>S</p>", delay=60),
        "/a": FakePage('<a href="/b">B</a>'),
    }
    fetcher = FakeFetcher(clock, pages, on_start={"/a": lambda: stop.set("interrupt")})

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, stop=stop, reporter=reporter
    )

    # The Checked URL still in flight at the stop is cancelled with the run, not waited for by a
    # sweep of the frontier from the top.
    assert (
        result.summary.state,
        result.summary.stop_reason,
        query(result.crawl_file, "SELECT url, fetch_state FROM urls ORDER BY id"),
        [data["reason"] for name, data in reporter.events if name == "stopping"],
    ) == (
        "stopped",
        "interrupt",
        [
            ("http://site.test/", "fetched"),
            ("http://other.test/slow", "queued"),
            ("http://site.test/a", "fetched"),
            ("http://site.test/b", "queued"),
        ],
        ["interrupt"],
    )


def test_a_crawl_run_from_another_thread_keeps_the_process_handlers(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    before = signal.getsignal(signal.SIGINT)
    results: list[CrawlResult] = []
    errors: list[BaseException] = []

    def crawl() -> None:
        try:
            results.append(
                crawl_result(
                    "http://site.test/",
                    clock=clock,
                    fetcher=FakeFetcher(clock, {"/": FakePage("<p>/</p>")}),
                )
            )
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=crawl)
    thread.start()
    thread.join(timeout=30)

    assert (
        [type(error).__name__ for error in errors],
        [result.summary.state for result in results],
        signal.getsignal(signal.SIGINT) is before,
    ) == ([], ["completed"], True)
