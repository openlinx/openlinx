"""The frontier: one request per URL, an end, the order, and what a kill keeps
(020-add-crawl-core D1; seam 3, and seam 1 for the kill)."""

import time
from pathlib import Path

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import await_event, start_cli_process
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


def _links_to_all_but(page: int) -> str:
    others = "".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 11) if n != page)
    return others + '<a href="/">Home</a>'


def test_each_url_is_requested_once(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/p1">P1</a>'),
                **{f"/p{n}": Page(body=_links_to_all_but(n)) for n in range(1, 11)},
            }
        )
    )

    crawled(server.url("/"))

    paths = [request.path for request in server.requests]
    expected = ["/", *(f"/p{n}" for n in range(1, 11))]
    assert {path: paths.count(path) for path in expected} == dict.fromkeys(expected, 1)


def test_a_link_cycle_ends(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a>'),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body='<a href="/a">A</a><a href="/">Home</a>'),
            }
        )
    )

    assert crawl_row(crawled(server.url("/")))["state"] == "completed"


def test_followed_urls_start_in_discovery_order(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/c">C</a><a href="/a">A</a><a href="/b">B</a>'),
                **{path: Page(body="<p>Page</p>") for path in ("/c", "/a", "/b")},
            }
        )
    )

    crawled(server.url("/"), "--concurrency", "1")

    assert [request.path for request in server.requests if request.path in {"/a", "/b", "/c"}] == [
        "/c",
        "/a",
        "/b",
    ]


# What each Page links to: every /pN to two URLs that no other Page links to, so a Page
# committed without the URLs it found shows as missing rows.
_KILL_PAGES = range(1, 31)
KILL_LINKS = {
    "/": [f"/p{n}" for n in _KILL_PAGES],
    **{f"/p{n}": [f"/p{n}/a", f"/p{n}/b"] for n in _KILL_PAGES},
}
KILLED_SITE = Site(
    routes={
        # Each /pN answers slowly, so the Crawl still runs when the test kills it.
        **{
            path: Page(
                body="".join(f'<a href="{link}">L</a>' for link in links),
                delay=0 if path == "/" else 0.2,
            )
            for path, links in KILL_LINKS.items()
        },
        **{f"/p{n}/{leaf}": Page(body="<p>L</p>") for n in _KILL_PAGES for leaf in "ab"},
    }
)


@pytest.mark.slow
def test_a_killed_crawl_leaves_no_half_recorded_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(KILLED_SITE)
    process = start_cli_process("crawl", server.url("/"))
    crawl_file = Path(await_event(process, "crawl_started")["crawl_file"])
    _await_parsed_pages(crawl_file, 10)

    process.kill()
    assert process.stdout is not None
    assert process.stderr is not None
    with process.stdout, process.stderr:
        process.wait(timeout=30)

    parsed = {url for (url,) in query(crawl_file, "SELECT url FROM urls WHERE parsed = 1")}
    recorded = {url for (url,) in query(crawl_file, "SELECT url FROM urls")}
    found = {
        path: [link for link in links if server.url(link) not in recorded]
        for path, links in KILL_LINKS.items()
        if server.url(path) in parsed
    }
    # At least one parsed /pN, whose URLs only its own unit records.
    assert (crawl_row(crawl_file)["state"], set(found) - {"/"} != set(), found) == (
        "running",
        True,
        {path: [] for path in found},
    )


def _await_parsed_pages(crawl_file: Path, count: int) -> None:
    """Once a reader sees `count` committed Pages that were parsed."""
    deadline = time.monotonic() + 30
    while query(crawl_file, "SELECT count(*) FROM urls WHERE parsed = 1")[0][0] < count:
        assert time.monotonic() < deadline, f"fewer than {count} parsed Pages were committed"
        time.sleep(0.05)
