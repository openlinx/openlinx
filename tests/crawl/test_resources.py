"""Resources: requested, never parsed unless in-Scope HTML (020-add-crawl-core D5; seam 3+6)."""

from pathlib import Path

import pytest

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


_PHOTO = Page(body="\xff\xd8\xff\xe0 JFIF", content_type="image/jpeg")


def _photo_rows(crawl_file: Path, *urls: str) -> list[tuple[object, ...]]:
    return query(
        crawl_file,
        "SELECT url, fetch_state, discovered_via FROM urls WHERE url IN (?, ?) ORDER BY id",
        list(urls),
    )


def test_an_image_that_another_page_hyperlinked_first_is_checked_beyond_the_depth_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a> <a href="/b">B</a>'),
                # A gallery Page links the full-size photo that the article Page shows.
                "/a": Page(body='<a href="/photo.jpg">Full size</a>'),
                # After /a's unit, so /a records the photo first; no unit is visible to the site.
                "/b": Page(
                    body='<a href="/next">Next</a> <img src="/photo.jpg">', after="/a", delay=0.5
                ),
                "/next": Page(body="<p>Next</p>"),
                "/photo.jpg": _PHOTO,
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "1")

    # /a recorded the photo before /b recorded /next, so /b's image raised it.
    assert _photo_rows(crawl_file, server.url("/photo.jpg"), server.url("/next")) == [
        (server.url("/photo.jpg"), "fetched", "image"),
        (server.url("/next"), "skipped", "hyperlink"),
    ]


@pytest.mark.slow
def test_a_resource_link_to_a_url_in_flight_leaves_the_provenance_its_dispatch_acted_on(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
                "/a": Page(body='<a href="/photo.jpg">Full size</a>'),
                # A check that answers only once the photo is requested, so its image Link
                # reaches the photo in flight, at the photo's own depth.
                "/late.html": Page(body='<img src="/photo.jpg">', after="/photo.jpg"),
                "/photo.jpg": Page(
                    body="\xff\xd8\xff\xe0 JFIF", content_type="image/jpeg", delay=2.0
                ),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT photo.fetch_state, photo.crawl_depth, photo.discovered_via, page.url "
        "FROM urls AS photo JOIN urls AS page ON page.id = photo.found_on_url_id "
        "WHERE photo.url = ?",
        [server.url("/photo.jpg")],
    ) == [("fetched", 2, "hyperlink", server.url("/a"))]
