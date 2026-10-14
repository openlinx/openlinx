"""Crawl Depth and the depth barrier (020-add-crawl-core D3; seam 3+6)."""

import pytest

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# Long against the few milliseconds a local request takes, short for a test.
SLOW = 2.0


@pytest.mark.slow
def test_the_shortest_path_wins_over_a_faster_longer_one(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/slow">S</a><a href="/a">A</a>'),
                "/slow": Page(body='<a href="/b">B</a>', delay=SLOW),
                "/a": Page(body='<a href="/x">X</a>'),
                "/x": Page(body='<a href="/b">B</a>'),
                "/b": Page(body="<p>B</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(crawl_file, "SELECT crawl_depth FROM urls WHERE url = ?", [server.url("/b")]) == [
        (2,)
    ]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("check", "slow_site"),
    [
        ('<img src="/slow.png">', Site(routes={"/slow.png": Page(body="PNG", delay=SLOW)})),
        (
            '<a href="http://other.test/slow.png">External</a>',
            Site(routes={"/slow.png": Page(body="PNG", delay=SLOW)}),
        ),
    ],
)
def test_a_slow_check_does_not_hold_the_next_depth(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts, check: str, slow_site: Site
) -> None:
    site = Site(
        routes={
            "/": Page(body=f'{check}<a href="/a">A</a>'),
            "/a": Page(body='<a href="/b">B</a>'),
            "/b": Page(body="<p>B</p>"),
            **slow_site.routes,
        }
    )
    hosts = fixture_hosts(site, slow_site)

    crawl_result("http://site.test/", resolver=hosts.resolver)

    (slow,) = [
        request
        for request in (*hosts.site.requests, *hosts.other.requests)
        if request.path == "/slow.png"
    ]
    (deeper,) = [request for request in hosts.site.requests if request.path == "/b"]
    assert deeper.received_at - slow.received_at < SLOW / 2


def test_urls_found_by_a_check_after_its_depth_are_crawled(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
                # In-Scope HTML behind an image Link: parsed after depth 1 has closed.
                "/late.html": Page(body='<a href="/found">F</a>', delay=SLOW / 2),
                "/a": Page(body="<p>A</p>"),
                "/found": Page(body="<p>F</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT fetch_state, crawl_depth FROM urls WHERE url = ?",
        [server.url("/found")],
    ) == [("fetched", 2)]


def test_a_resource_is_one_deeper_than_its_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/about">About</a>'),
                "/about": Page(body='<img src="/i.png">'),
                "/i.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT crawl_depth FROM urls WHERE url = ?", [server.url("/i.png")]
    ) == [(2,)]


@pytest.mark.slow
def test_a_late_check_lowers_the_depth_of_a_url_still_queued(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
                # Ends at depth 1's check time, while /hold keeps depth 3 from opening.
                "/late.html": Page(body='<a href="/x">X</a>', delay=SLOW / 2),
                "/a": Page(body='<a href="/b">B</a><a href="/hold">H</a>'),
                "/b": Page(body='<a href="/x">X</a>'),
                "/hold": Page(body="<p>H</p>", delay=SLOW),
                "/x": Page(body="<p>X</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT fetch_state, crawl_depth FROM urls WHERE url = ?", [server.url("/x")]
    ) == [("fetched", 2)]
