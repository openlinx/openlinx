"""The network pause's count (020-add-crawl-core D16; seams 2, 3 and 4)."""

from typing import Any

import pytest

from spider.crawl.engine.pause import pause_after, probe_times
from spider.output.reporter import Collected
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.fetcher import FakeFetcher, FakePage
from tests.support.workspace import TempWorkspace

_PAIRS = range(1, 21)


def test_a_response_resets_the_count(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # Twenty requests without a response, but a response between any two.
    links = "".join(f'<a href="/down/{n}">Down</a><a href="/up/{n}">Up</a>' for n in _PAIRS)
    server = fixture_site(
        Site(
            routes={
                "/": Page(body=links),
                **{f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in _PAIRS},
                **{f"/up/{n}": Page(body="<p>Up</p>") for n in _PAIRS},
            }
        )
    )

    result = crawl_result(server.url("/"), concurrency=1, network_wait=0)

    assert (result.summary.state, result.counts.errors) == ("completed", 20)


def test_the_urls_of_an_internal_origin_whose_robots_txt_gets_no_response_count(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    # blog.site.test does not resolve, so its robots.txt gets no response and its URLs none.
    links = "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in _PAIRS)
    hosts = fixture_hosts(Site(routes={"/": Page(body=links)}), Site(routes={}))

    result = crawl_result(
        "http://site.test/", resolver=hosts.resolver, scope="subdomains", network_wait=0
    )

    assert (result.summary.state, result.summary.stop_reason) == ("failed", "site_unreachable")


def test_a_seed_whose_robots_txt_answers_counts_like_any_url(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # robots.txt answers 404, so the Seed's origin has answered before its home page resets.
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>", reset_after=0)}))

    result = crawl_result(server.url("/"), network_wait=0)

    assert (result.summary.state, result.counts.errors) == ("completed", 1)


@pytest.mark.parametrize(("concurrency", "requests"), [(1, 8), (4, 8), (5, 10), (50, 100)])
def test_the_requests_in_a_row_that_pause_the_crawl(concurrency: int, requests: int) -> None:
    assert pause_after(concurrency) == requests


@pytest.mark.parametrize(("down", "state"), [(7, "completed"), (8, "failed")])
def test_the_count_trips_at_eight_requests_in_a_row_at_concurrency_one(
    temp_workspace: TempWorkspace, fixture_site: StartSite, down: int, state: str
) -> None:
    downs = range(1, down + 1)
    links = "".join(f'<a href="/down/{n}">Down</a>' for n in downs) + '<a href="/up">Up</a>'
    server = fixture_site(
        Site(
            routes={
                "/": Page(body=links),
                **{f"/down/{n}": Page(body="<p>Down</p>", reset_after=0) for n in downs},
                "/up": Page(body="<p>Up</p>"),
            }
        )
    )

    result = crawl_result(server.url("/"), concurrency=1, network_wait=0)

    assert result.summary.state == state


@pytest.mark.parametrize(
    ("network_wait", "times"),
    [
        (200, (5, 10, 20, 40, 100, 160)),
        (30, (5, 10, 20)),
        # A probe exactly at the wait still starts.
        (40, (5, 10, 20, 40)),
        (100, (5, 10, 20, 40, 100)),
        (4, ()),
        (0, ()),
        (1800, (5, 10, 20, 40, *range(100, 1781, 60))),
    ],
)
def test_probes_back_off_to_once_a_minute(network_wait: int, times: tuple[int, ...]) -> None:
    assert probe_times(network_wait) == times


def _dead_section() -> dict[str, FakePage]:
    """/ links to /down/1 to /down/20, which never answer, and then to /p1."""
    links = "".join(f'<a href="/down/{n}">Down {n}</a>' for n in _PAIRS) + '<a href="/p1">P1</a>'
    return {
        "/": FakePage(links),
        **{f"/down/{n}": FakePage("", fails="connection_error") for n in _PAIRS},
        "/p1": FakePage("<p>P1</p>"),
    }


def test_a_dead_section_does_not_stop_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, _dead_section()), concurrency=1
    )
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    assert (
        result.summary.state,
        {states[f"http://site.test/down/{n}"] for n in _PAIRS},
        states["http://site.test/p1"],
        [warning.code for warning in result.warnings],
    ) == ("completed", {"error"}, "fetched", ["network_paused"])


def test_network_paused_counts_the_pauses_and_their_seconds(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    # Eight failures pause it twice; the first probe, 5 seconds in, ends each pause.
    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=FakeFetcher(clock, _dead_section()), concurrency=1
    )

    assert [w.details for w in result.warnings if w.code == "network_paused"] == [
        {"count": 2, "total_seconds": 10.0}
    ]


def test_probes_do_not_count_toward_the_url_limit(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()

    # The Seed, the twenty dead URLs and /p1 are 22 URL requests; the two probes are not.
    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, _dead_section()),
        concurrency=1,
        max_urls=22,
    )

    assert query(
        result.crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", ["http://site.test/p1"]
    ) == [("fetched",)]


_TWENTY = range(1, 21)


def _outage_site() -> dict[str, FakePage]:
    """/ links to /p1 to /p20; /p1 answers a second later, so the outage that a test starts at
    one second begins with /p2."""
    return {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY)),
        "/p1": FakePage("<p>P1</p>", delay=1),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in _TWENTY if n > 1},
    }


def _pause_events(reporter: Collected) -> list[tuple[str, dict[str, Any]]]:
    return [
        (name, data) for name, data in reporter.events if name in ("crawl_paused", "crawl_resumed")
    ]


def test_an_outage_pauses_and_resumes_the_crawl(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )

    assert (
        [(name, data.get("outcome")) for name, data in _pause_events(reporter)],
        result.summary.state,
    ) == ([("crawl_paused", None), ("crawl_resumed", "outage")], "completed")


def test_the_pause_events_say_why_which_urls_and_how_long(temp_workspace: TempWorkspace) -> None:
    clock, reporter = FakeClock(), Collected()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, reporter=reporter, concurrency=1
    )

    # Paused at one second by /p2 to /p9; the probes at 6, 11 and 21 fail, the one at 41 answers.
    assert _pause_events(reporter) == [
        (
            "crawl_paused",
            {
                "crawl_id": result.crawl_id,
                "reason": "connection_error",
                "urls": [f"http://site.test/p{n}" for n in range(2, 10)],
            },
        ),
        ("crawl_resumed", {"crawl_id": result.crawl_id, "duration_s": 40.0, "outcome": "outage"}),
    ]


def test_requests_that_fail_while_paused_are_requested_again_within_the_url_limit(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # Each answer, or failure, takes a little longer than the one before, so requests are still
    # in flight when the pause begins.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 31))),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>", delay=0.5 + n / 100) for n in range(1, 31)},
    }

    result = crawl_result(
        "http://site.test/",
        clock=clock,
        fetcher=FakeFetcher(clock, pages, outages=[(1, 30)]),
        concurrency=4,
        max_urls=25,
    )
    requested = query(
        result.crawl_file,
        "SELECT fetch_state, count(*) FROM urls WHERE fetch_state != 'queued' GROUP BY 1",
    )

    # 25 distinct URLs, those in flight when the pause began and the eight that made up the
    # count among them, all fetched once the outage is over.
    assert requested == [("fetched", 25)]


def test_urls_that_failed_in_an_outage_are_requested_again(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    fetcher = FakeFetcher(clock, _outage_site(), outages=[(1, 30)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)
    pages = query(
        result.crawl_file, "SELECT fetch_state, crawl_depth FROM urls WHERE url LIKE '%/p%'"
    )

    # Requested again at the depth they were found at.
    assert set(pages) == {("fetched", 1)}


def test_an_outage_requeues_a_url_once_a_run(temp_workspace: TempWorkspace) -> None:
    clock = FakeClock()
    # /p2 to /p9 fail until 80 seconds: requested again at 41 when the first outage ends, they
    # fail into a second outage, which ends at 81 and must not re-queue them again.
    pages = {
        **_outage_site(),
        **{f"/p{n}": FakePage("", fails="connection_error", until=80) for n in range(2, 10)},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30), (42, 80)])

    result = crawl_result("http://site.test/", clock=clock, fetcher=fetcher, concurrency=1)
    states = dict(query(result.crawl_file, "SELECT url, fetch_state FROM urls"))

    assert (
        {states[f"http://site.test/p{n}"] for n in range(2, 10)},
        {states[f"http://site.test/p{n}"] for n in range(10, 21)},
    ) == ({"error"}, {"fetched"})


def test_an_outage_drops_the_failed_robots_txt_verdict_of_an_internal_origin(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    posts = range(1, 9)
    # /p1 answers at one second, when the outage begins, so the blog's robots.txt fails.
    pages = {
        "/": FakePage('<a href="/p1">P1</a>'),
        "/p1": FakePage(
            "".join(f'<a href="http://blog.site.test/{n}">Post</a>' for n in posts), delay=1
        ),
        **{f"http://blog.site.test/{n}": FakePage(f"<p>Post {n}</p>") for n in posts},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, 30)])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, scope="subdomains"
    )

    assert set(
        query(result.crawl_file, "SELECT fetch_state FROM urls WHERE url LIKE 'http://blog.%'")
    ) == {("fetched",)}


def test_a_crawl_that_waits_longer_than_the_network_wait_fails(
    temp_workspace: TempWorkspace,
) -> None:
    clock = FakeClock()
    # / answers at one second, and from then on nothing does: the pause begins at one second.
    pages = {
        "/": FakePage("".join(f'<a href="/p{n}">P{n}</a>' for n in _TWENTY), delay=1),
        **{f"/p{n}": FakePage(f"<p>P{n}</p>") for n in _TWENTY},
    }
    fetcher = FakeFetcher(clock, pages, outages=[(1, float("inf"))])

    result = crawl_result(
        "http://site.test/", clock=clock, fetcher=fetcher, concurrency=1, network_wait=30
    )
    probes = [at for url, at in fetcher.starts if url == "http://site.test/" and at > 0]

    assert (probes, result.summary.state, result.summary.stop_reason) == (
        [6, 11, 21],
        "failed",
        "site_unreachable",
    )
