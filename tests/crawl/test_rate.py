"""Politeness in time: the rate and Crawl-delay (020-add-crawl-core D7; fake timing)."""

from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

# The Seed and the four Pages it links to, on one host.
FOUR_LINKS = {
    "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 5))),
    **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in range(1, 5)},
}


def test_requests_to_a_host_are_spaced_by_the_rate(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, FOUR_LINKS)

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, rate=2)

    assert [start for _, start in fetcher.starts] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]


# robots.txt asks for 30 seconds between requests, and the Seed links to three Pages.
CRAWL_DELAY_30 = {
    "/robots.txt": FakePage("User-agent: *\nCrawl-delay: 30\n", "text/plain"),
    "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 4))),
    **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in range(1, 4)},
}


def test_crawl_delay_is_not_applied(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, CRAWL_DELAY_30)

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher)

    assert sorted(path for path, start in fetcher.starts if start < 1) == [
        "/",
        "/p1",
        "/p2",
        "/p3",
        "/robots.txt",
    ]


# The Seed links to its own host twice, once with the trailing dot of a fully qualified name.
TRAILING_DOT = {
    "/": FakePage('<a href="http://site.test./p1">P1</a> <a href="/p2">P2</a>'),
    "/p1": FakePage("<p>P1</p>"),
    "/p2": FakePage("<p>P2</p>"),
}


def test_a_host_with_a_trailing_dot_shares_the_rate_turn_of_the_host(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, TRAILING_DOT)

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, rate=2)

    # One server: its robots.txt twice, as two origins, and the three Pages, one turn each.
    assert sorted(start for _, start in fetcher.starts) == [0.0, 0.5, 1.0, 1.5, 2.0]


# Each host's first request starts at once, and its second one 0.5 s later, side by side.
TWO_HOSTS = {
    "/": FakePage('<a href="/p">P</a> <a href="http://other.test/q">Q</a>'),
    "/p": FakePage("<p>P</p>"),
    "/q": FakePage("<p>Q</p>"),
}


def test_two_hosts_wait_for_their_turns_at_the_same_time(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, TWO_HOSTS)

    crawl_result("http://site.test/", clock=clock, fetcher=fetcher, rate=2)

    # site.test: robots.txt, /, /p; other.test: robots.txt, /q, each 0.5 s after its last.
    assert sorted(start for _, start in fetcher.starts) == [0.0, 0.5, 0.5, 1.0, 1.0]
