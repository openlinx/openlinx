"""Retries in time: the backoff between attempts (022-add-fetch-policy, fetching; fake timing)."""

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
