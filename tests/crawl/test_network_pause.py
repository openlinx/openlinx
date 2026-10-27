"""The network pause's count (020-add-crawl-core D16; seams 2, 3 and 4)."""

import pytest

from spider.crawl.engine.pause import pause_after, probe_times
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
