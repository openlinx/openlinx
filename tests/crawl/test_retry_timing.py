"""Retries in time: the backoff between attempts (022-add-fetch-policy, fetching; fake timing)."""

import pytest

from spider.crawl.fetch.politeness import RateGate
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace


def test_retries_wait_one_and_then_two_seconds(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/down": FakePage("<h1>Internal Server Error</h1>", status=500)})

    crawl_result("http://site.test/down", clock=clock, fetcher=fetcher)

    assert [start for path, start in fetcher.starts if path == "/down"] == [0.0, 1.0, 3.0]


def test_the_backoff_doubles_with_each_retry(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, {"/down": FakePage("<h1>Internal Server Error</h1>", status=500)})

    crawl_result("http://site.test/down", clock=clock, fetcher=fetcher, retries=3)

    assert [start for path, start in fetcher.starts if path == "/down"] == [0.0, 1.0, 3.0, 7.0]


def _starts(fetcher: FakeFetcher, path: str) -> list[float]:
    return [start for requested, start in fetcher.starts if requested == path]


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
    await gate.wait_turn("site.test")

    gate.pause("site.test", 7)
    await gate.started("site.test")

    assert clock.monotonic() == 7.0
