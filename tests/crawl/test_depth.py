"""Verify Crawl Depth and the depth barrier over HTTP and stored rows."""

import json
import os
from pathlib import Path

import pytest

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import CRAWL_PROCESS_TIMEOUT, run_cli_process
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.sites import LATE_SHORTER_PATH
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
                # The check answers once depth 2 has started, after /b's unit, while /hold
                # keeps depth 3 from opening; no unit is visible to the site, so a delay.
                "/late.html": Page(body='<a href="/x">X</a>', after="/b", delay=SLOW / 2),
                "/a": Page(body='<a href="/b">B</a><a href="/hold">H</a>'),
                "/b": Page(body='<a href="/b2">B2</a><a href="/x">X</a>'),
                "/b2": Page(body="<p>B2</p>"),
                "/hold": Page(body="<p>H</p>", delay=SLOW),
                # Slow, so /b2, read once depth 2 has ended with the lowered /x, starts well
                # after it (022-add-fetch-policy D2: a pass reads the open depth again from its
                # top).
                "/x": Page(body="<p>X</p>", delay=SLOW / 4),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    # /b recorded /x after /b2, so /x was queued at depth 3 before the check lowered it.
    assert query(
        crawl_file,
        "SELECT url, fetch_state, crawl_depth FROM urls WHERE url IN (?, ?) ORDER BY id",
        [server.url("/b2"), server.url("/x")],
    ) == [(server.url("/b2"), "fetched", 3), (server.url("/x"), "fetched", 2)]
    # Dispatched at depth 2, before depth 3 opened, so the check lowered it while it was queued.
    started = {request.path: request.received_at for request in server.requests}
    assert started["/b2"] - started["/x"] >= SLOW / 4


@pytest.mark.slow
def test_a_late_check_gives_a_url_skipped_beyond_the_depth_limit_its_shorter_path(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(LATE_SHORTER_PATH)

    crawl_file = crawled(server.url("/"), "--max-depth", "2")

    assert query(
        crawl_file, "SELECT fetch_state, crawl_depth FROM urls WHERE url = ?", [server.url("/c")]
    ) == [("fetched", 2)]


def test_links_beyond_the_limit_are_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a>'),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body="<p>B</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "1")

    assert query(crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/b")]) == [
        ("max_depth",)
    ]


@pytest.mark.parametrize(
    ("source", "flags"),
    [
        pytest.param("[Crawl]\nmax_depth = {decimal}", ("--max-depth", "0"), id="decimal"),
        pytest.param("[Crawl]\nmax_depth = {hexadecimal}", ("--max-depth", "0"), id="hex"),
        pytest.param(
            "[Crawl]\nmax_depth = 0\nconcurrency = {decimal}",
            ("--concurrency", "5"),
            id="explicit-default",
        ),
        pytest.param(
            "[Crawl]\nmax_depth = 0\n[crawl]\nmax_depth = {decimal}", (), id="shadowed-table"
        ),
    ],
)
def test_a_discarded_wide_decimal_does_not_block_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, flags: tuple[str, ...]
) -> None:
    server = fixture_site(
        Site(routes={"/": Page(body='<a href="/child">Child</a>'), "/child": Page(body="Child")})
    )
    (temp_workspace.root / "openlinx.toml").write_text(
        source.format(decimal="9" * 4301, hexadecimal=f"{10**4301 - 1:#x}") + "\n",
        encoding="utf-8",
    )

    result = run_cli_process(
        "crawl",
        server.url("/"),
        *flags,
        env={**os.environ, "PYTHONINTMAXSTRDIGITS": "640"},
        timeout=CRAWL_PROCESS_TIMEOUT,
    )

    assert result.exit_code == 0, result.stderr
    output = result.json()
    assert output["state"] == "completed"
    file = Path(output["crawl_file"])
    config = json.loads(crawl_row(file)["config"])["crawl"]
    assert (config["max_depth"], config["concurrency"]) == (0, 5)
    assert query(file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/child")]) == [
        ("max_depth",)
    ]
    assert [request.path for request in server.requests] == ["/robots.txt", "/"]


@pytest.mark.slow
def test_the_urls_found_on_a_url_lowered_in_flight_are_one_deeper_than_it(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
                # Answers only once /x is requested, so it can lower /x only in flight.
                "/late.html": Page(body='<a href="/x">X</a>', after="/x"),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body='<a href="/b2">B2</a><a href="/x">X</a>'),
                "/b2": Page(body="<p>B2</p>"),
                # In flight at depth 3 when the late check lowers it to 2.
                "/x": Page(body='<a href="/y">Y</a>', delay=SLOW),
                "/y": Page(body="<p>Y</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    # /b recorded /x after /b2, so /x was queued at depth 3 before the check lowered it.
    assert query(
        crawl_file,
        "SELECT url, crawl_depth FROM urls WHERE url IN (?, ?, ?) ORDER BY id",
        [server.url("/b2"), server.url("/x"), server.url("/y")],
    ) == [(server.url("/b2"), 3), (server.url("/x"), 2), (server.url("/y"), 3)]
    # The lowered /x keeps the late check's provenance, which its depth agrees with.
    assert query(
        crawl_file,
        "SELECT page.url FROM urls AS x JOIN urls AS page ON page.id = x.found_on_url_id "
        "WHERE x.url = ?",
        [server.url("/x")],
    ) == [(server.url("/late.html"),)]


def test_a_resource_of_an_html_resource_is_beyond_the_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/pic">'),
                "/pic": Page(body='<img src="/i.png">'),
            }
        )
    )

    crawl_file = crawl_result(server.url("/"), max_depth=0).crawl_file

    assert query(
        crawl_file,
        "SELECT url, fetch_state, skip_reason FROM urls WHERE url IN (?, ?) ORDER BY id",
        [server.url("/pic"), server.url("/i.png")],
    ) == [(server.url("/pic"), "fetched", None), (server.url("/i.png"), "skipped", "max_depth")]
