"""Retries in time: the backoff between attempts (022-add-fetch-policy, fetching; fake timing)."""

from functools import partial
from typing import Any

import pytest

from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.fetch.politeness import RateGate
from openlinx.output.reporter import Collected
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace


def test_retries_wait_one_and_then_two_seconds(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/down": FakePage("<h1>Internal Server Error</h1>", status=500)})

    crawl_result("http://site.test/down", clock=clock, fetcher=fetcher)

    assert [start for path, start in fetcher.path_starts if path == "/down"] == [0.0, 1.0, 3.0]


def test_the_backoff_doubles_with_each_retry(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/down": FakePage("<h1>Internal Server Error</h1>", status=500)})

    crawl_result("http://site.test/down", clock=clock, fetcher=fetcher, retries=3)

    assert [start for path, start in fetcher.path_starts if path == "/down"] == [0.0, 1.0, 3.0, 7.0]


def _starts(fetcher: FakeFetcher, path: str) -> list[float]:
    return [start for requested, start in fetcher.path_starts if requested == path]


def test_retry_after_pauses_the_host(temp_workspace: TempWorkspace) -> None:
    # A shop's API gateway rate-limits /a; /b on the same host must wait out the pause too.
    clock = FakeClock()
    fetcher = FakeFetcher(
        clock,
        {
            "/": FakePage('<a href="/a">A</a><a href="/b">B</a>'),
            "/a": [
                FakePage("<h1>Too Many Requests</h1>", status=429, headers=(("Retry-After", "7"),)),
                FakePage("<title>A</title>"),
            ],
            "/b": FakePage("<title>B</title>"),
        },
    )

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)

    assert (_starts(fetcher, "/a"), _starts(fetcher, "/b")) == ([0.0, 7.0], [7.0])


def test_a_429_pauses_the_host_without_a_retry(temp_workspace: TempWorkspace) -> None:
    # The same gateway, crawled with no retries: /a is given up, but /b still waits.
    clock = FakeClock()
    fetcher = FakeFetcher(
        clock,
        {
            "/": FakePage('<a href="/a">A</a><a href="/b">B</a>'),
            "/a": FakePage(
                "<h1>Too Many Requests</h1>", status=429, headers=(("Retry-After", "7"),)
            ),
            "/b": FakePage("<title>B</title>"),
        },
    )

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, retries=0)

    assert (_starts(fetcher, "/a"), _starts(fetcher, "/b")) == ([0.0], [7.0])


@pytest.mark.parametrize(
    ("status", "headers", "wait"),
    [
        # A 429 without Retry-After waits 10 seconds.
        (429, (), 10.0),
        # A 503 for maintenance that names its end in seconds.
        (503, (("Retry-After", "4"),), 4.0),
        # Retry-After as an HTTP date, 5 seconds after the response.
        (429, (("Retry-After", "Thu, 01 Jan 2026 00:00:05 GMT"),), 5.0),
        # A Retry-After of ten minutes waits the cap of 120 seconds.
        (429, (("Retry-After", "600"),), 120.0),
    ],
)
def test_a_retry_after_or_a_429_sets_the_wait_before_the_retry(
    temp_workspace: TempWorkspace,
    status: int,
    headers: tuple[tuple[str, str], ...],
    wait: float,
) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(
        clock,
        {"/a": [FakePage("<h1>Wait</h1>", status=status, headers=headers), FakePage("<p>A</p>")]},
    )

    crawl_result("http://site.test/a", clock=clock, fetcher=fetcher)

    assert _starts(fetcher, "/a") == [0.0, wait]


async def test_a_request_waiting_for_the_global_cap_when_its_host_pauses_starts_after_it() -> None:
    # Its turn came before the 429 arrived; the permit it waited for frees as the pause starts.
    clock = FakeClock()
    gate = RateGate(clock, None)
    assert gate.reserve_turn("site.test") == 0.0

    gate.pause("site.test", 7)
    await gate.started("site.test")

    assert clock.monotonic() == 7.0


class _Timeline(Collected):
    """The Crawl's events, in one list with the requests a fake Fetcher saw start."""

    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self._timeline = timeline

    def event(self, name: str, **data: Any) -> None:
        self._timeline.append(name)
        super().event(name, **data)


def test_a_network_that_goes_down_pauses_the_crawl_before_the_retries(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    timeline: list[str] = []
    links = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 21))
    refused = {f"/p{n}": FakePage("", fails="connection_refused") for n in range(1, 21)}
    fetcher = FakeFetcher(
        clock,
        {"/": FakePage(links), **refused},
        on_start={path: partial(timeline.append, path) for path in refused},
    )

    crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=fetcher,
        reporter=_Timeline(timeline),
        concurrency=1,
    )

    # --concurrency 1 pauses at 8 URLs in a row: their first attempts, no retry among them.
    before = timeline[: timeline.index("crawl_paused")]
    assert [entry for entry in before if entry.startswith("/")] == [f"/p{n}" for n in range(1, 9)]


def test_a_request_that_fails_during_a_network_pause_is_not_retried(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # / answers at 12 seconds, and from then on nothing does: /p1 to /p8 fail at once, each
    # counted at its first attempt, and pause the Crawl with their retries due a second later.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 21)), delay=12),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in range(1, 21)},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(12, float("inf"))])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, network_wait=30
    )
    starts = [(path, at) for path, at in fetcher.path_starts if path.startswith("/p")]
    states = query(
        result.crawl_file,
        "SELECT fetch_state, attempt_count, count(*) FROM urls WHERE url LIKE '%/p%' GROUP BY 1, 2",
    )

    # The eight of the count keep their first failure, which a continue requests again.
    assert (starts, states) == (
        [(f"/p{n}", 12) for n in range(1, 9)],
        [("error", 1, 8), ("queued", 0, 12)],
    )


def test_a_retry_under_way_outlasts_the_url_limit(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": FakePage('<a href="/a">A</a><a href="/b">B</a><a href="/c">C</a>'),
        "/a": [FakePage("", status=503), FakePage("<p>A</p>")],
    }

    # /c is refused at the limit while /a waits out its one-second backoff.
    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages), max_urls=3
    )

    assert (
        result.summary.stop_reason,
        query(
            result.crawl_file,
            "SELECT status_code, attempt_count FROM urls WHERE url = 'http://site.test/a'",
        ),
    ) == ("max_urls", [(200, 2)])


@pytest.mark.parametrize("path", ["/", "/robots.txt"])
def test_a_stop_cuts_a_pending_retry_and_keeps_its_url_queued(
    temp_workspace: TempWorkspace, path: str
) -> None:
    clock, stop = FakeClock(), StopSignal()
    # The Seed's own 503, or its robots.txt's, arrives with the stop.
    pages = {path: [FakePage("", status=503), FakePage("<p>Home</p>")]}
    fetcher = FakeFetcher(clock, pages, on_answer={path: lambda: stop.set("interrupt")})

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, stop=stop)

    assert (
        result.summary.stop_reason,
        query(result.crawl_file, "SELECT fetch_state, status_code FROM urls WHERE id = 1"),
    ) == ("interrupt", [("queued", None)])


def test_a_retry_the_closed_gate_ends_outside_the_count_is_requested_after_the_pause(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    external = "http://cdn.test/app.js"
    # The External script answers 503 at once, and its retry is due a second later, when
    # /p1 to /p8 have paused the Crawl; the Seed answers the first probe, at 5 seconds.
    pages: dict[str, FakePage | list[FakePage]] = {
        "/": FakePage(
            f'<script src="{external}"></script>'
            + "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 9))
        ),
        **{f"/p{n}": FakePage("", fails="connection_refused") for n in range(1, 9)},
        external: [FakePage("", status=503), FakePage("", content_type="text/javascript")],
    }

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, pages), concurrency=1
    )

    # Its 503 is no final answer: requested afresh after the pause, it gets its 200.
    assert query(
        result.crawl_file,
        "SELECT fetch_state, status_code, attempt_count FROM urls WHERE url = 'http://cdn.test/app.js'",
    ) == [("fetched", 200, 1)]
