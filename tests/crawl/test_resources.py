"""Resources: requested, never parsed unless in-Scope HTML (020-add-crawl-core D5; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_an_image_is_checked_but_not_parsed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/logo.png">'),
                "/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT status_code, parsed FROM urls WHERE url = ?", [server.url("/logo.png")]
    ) == [(200, 0)]


def test_a_broken_image_is_recorded(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<img src="/missing.png">')}))

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT status_code FROM urls WHERE url = ?", [server.url("/missing.png")]
    ) == [(404,)]


def test_resources_are_checked_beyond_the_depth_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/logo.png"><a href="/about">About</a>'),
                "/logo.png": Page(body="PNG", content_type="image/png"),
                "/about": Page(body="<p>About</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "0")

    assert query(
        crawl_file, "SELECT fetch_state FROM urls WHERE url = ?", [server.url("/logo.png")]
    ) == [("fetched",)]


def test_a_resource_two_deeper_than_the_depth_limit_is_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<script src="/j/x.js"></script>'),
                # In-Scope HTML behind a Resource Link is parsed, so its own Resources are found.
                "/j/x.js": Page(body='<script src="/j/j/x.js"></script>'),
                "/j/j/x.js": Page(body="<p>J</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "0")

    assert query(
        crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/j/j/x.js")]
    ) == [("max_depth",)]


def test_an_image_a_page_also_hyperlinks_is_checked_beyond_the_depth_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/x.png">X</a><img src="/x.png">'),
                "/x.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "0")

    assert query(
        crawl_file,
        "SELECT discovered_via, fetch_state FROM urls WHERE url = ?",
        [server.url("/x.png")],
    ) == [("image", "fetched")]
