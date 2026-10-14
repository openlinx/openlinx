"""Scope over HTTP and Section Crawls (020-add-crawl-core D4, crawling; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_pages_inside_the_folder_are_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/blog/": Page(body='<a href="/blog/post">Post</a>'),
                "/blog/post": Page(body="<p>Post</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/blog/"), "--scope", "subfolder")

    assert query(
        crawl_file, "SELECT in_scope, parsed FROM urls WHERE url = ?", [server.url("/blog/post")]
    ) == [(1, 1)]


def test_pages_outside_the_folder_are_checked_but_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/blog/": Page(body='<a href="/shop/">Shop</a>'),
                "/shop/": Page(body='<a href="/shop/item">Item</a>'),
                "/shop/item": Page(body="<p>Item</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/blog/"), "--scope", "subfolder")

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, parsed FROM urls WHERE url = ?",
            [server.url("/shop/")],
        ),
        query(crawl_file, "SELECT id FROM urls WHERE url = ?", [server.url("/shop/item")]),
    ) == ([("fetched", 0)], [])
