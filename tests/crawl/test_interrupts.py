"""Stopping a Crawl with an interrupt (020-add-crawl-core D10, D16)."""

import json
import signal
import sys
import threading
import time

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
    stdout, stderr = process.communicate(timeout=30)

    result = json.loads(stdout)
    events = [json.loads(line) for line in stderr.splitlines()]
    stopping = [e["data"]["reason"] for e in events if e.get("event") == "stopping"]
    assert (process.returncode, result["state"], result["stop_reason"], stopping) == (
        130,
        "stopped",
        "interrupt",
        ["interrupt"],
    )


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
