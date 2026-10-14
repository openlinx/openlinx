"""Scope over HTTP and Section Crawls (020-add-crawl-core D4, crawling; seam 3+6)."""

import json

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace

# The fixture's other.test, which these Crawls never link to.
NO_OTHER_SITE = Site(routes={})


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


def test_a_url_that_matches_no_include_pattern_is_checked_but_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/blog/": Page(body='<a href="/news/n">News</a>'),
                "/news/n": Page(body="<p>News</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/blog/"), "--include", "/blog/")

    assert query(
        crawl_file,
        "SELECT fetch_state, in_scope, parsed FROM urls WHERE url = ?",
        [server.url("/news/n")],
    ) == [("fetched", 0, 0)]


def test_an_include_pattern_makes_a_section_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/blog/": Page(body="<p>Blog</p>")}))

    crawl_file = crawled(server.url("/blog/"), "--include", "/blog/")

    assert crawl_row(crawl_file)["section_crawl"] == 1


def test_exclude_patterns_alone_do_not_make_a_section_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>Home</p>")}))

    result = run_cli("crawl", server.url("/"), "--exclude", "/tag/")

    assert (result.exit_code, result.json()["section_crawl"]) == (0, False)


def test_a_subfolder_scope_is_recorded(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(Site(routes={"/blog/": Page(body="<p>Blog</p>")}), NO_OTHER_SITE)

    result = crawl_result(
        "http://site.test/blog/", resolver=hosts.resolver, scope="subfolder", exclude=["/draft"]
    )

    assert json.loads(crawl_row(result.crawl_file)["scope"]) == {
        "mode": "subfolder",
        "hosts": ["site.test", "www.site.test"],
        "folder": "/blog/",
        "include": [],
        "exclude": ["/draft"],
    }
