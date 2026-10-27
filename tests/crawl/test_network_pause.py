"""The network pause's count (020-add-crawl-core D16; seams 2, 3 and 4)."""

import pytest

from spider.crawl.engine.pause import pause_after
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
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
