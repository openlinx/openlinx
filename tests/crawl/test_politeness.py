"""Politeness limits (020-add-crawl-core D7; seam 4, and fake timing through the Crawl
Service)."""

import pytest

from spider.crawl.fetch.politeness import global_cap
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.pages import BackloggedPool
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(("concurrency", "cap"), [(1, 20), (5, 20), (6, 24), (25, 100), (50, 100)])
def test_the_global_cap_is_four_times_the_concurrency_within_20_to_100(
    concurrency: int, cap: int
) -> None:
    assert global_cap(concurrency) == cap


def test_the_global_cap_bounds_requests_across_hosts(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    links = [f"http://h{n}.test/p{n}" for n in range(30)]
    pages = {
        "/": FakePage("".join(f'<a href="{link}">L</a>' for link in links)),
        **{f"/p{n}": FakePage("<p>P</p>", delay=1) for n in range(30)},
    }
    fetcher = FakeFetcher(clock, pages)

    # A parse pool's backlog lets more URL tasks run than the cap, so only the cap bounds them.
    crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, pages=lambda: BackloggedPool(10)
    )

    assert (
        fetcher.most_in_flight,
        sorted(path for path, _ in fetcher.path_starts if path != "/robots.txt"),
    ) == (
        20,
        sorted(["/", *(f"/p{n}" for n in range(30))]),
    )
