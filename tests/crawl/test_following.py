"""Which Links the Crawl follows, over HTTP (020-add-crawl-core D5, crawling; seam 3+6)."""

from pathlib import Path

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _state(crawl_file: Path, url: str) -> list[tuple[object, ...]]:
    return query(
        crawl_file, "SELECT fetch_state, skip_reason, discovered_via FROM urls WHERE url = ?", [url]
    )


def test_a_meta_refresh_target_is_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/old">Old</a>'),
                "/old": Page(body='<meta http-equiv="refresh" content="0; url=/new">'),
                "/new": Page(body="<p>New</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/new")) == [("fetched", None, "meta_refresh")]


def test_amphtml_targets_are_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body='<link rel="amphtml" href="/amp/">')}))

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/amp/")) == [
        ("skipped", "link_type_not_followed", "amphtml")
    ]


def test_a_canonical_in_an_http_header_is_followed(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(body='<a href="/doc.pdf">Doc</a>'),
                "/doc.pdf": Page(
                    body="%PDF-1.7",
                    content_type="application/pdf",
                    headers=[("Link", '<http://site.test/doc>; rel="canonical"')],
                ),
                "/doc": Page(body="<p>Doc</p>"),
            }
        ),
        Site(routes={}),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert _state(crawl_file, "http://site.test/doc") == [("fetched", None, "canonical")]


def test_an_http_refresh_target_is_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/old">Old</a>'),
                "/old": Page(body="<p>Old</p>", headers=[("Refresh", "0; url=/new")]),
                "/new": Page(body="<p>New</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/new")) == [("fetched", None, "http_refresh")]


def test_links_on_an_error_page_are_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/gone">Gone</a>'),
                "/gone": Status(404, body='<a href="/secret">Secret</a>'),
                "/secret": Page(body="<p>Secret</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert (
        query(crawl_file, "SELECT parsed FROM urls WHERE url = ?", [server.url("/gone")]),
        query(crawl_file, "SELECT id FROM urls WHERE url = ?", [server.url("/secret")]),
    ) == ([(0,)], [])


def test_a_nofollow_link_is_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a rel="nofollow" href="/private">Private</a>'),
                "/private": Page(body="<p>Private</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/private")) == [("skipped", "nofollow", "hyperlink")]


def test_a_page_level_nofollow_applies_to_every_hyperlink(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<meta name="robots" content="noindex, nofollow"><a href="/x">X</a>'
                ),
                "/x": Page(body="<p>X</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/x")) == [("skipped", "nofollow", "hyperlink")]


def test_a_nofollow_target_reached_through_a_followed_link_is_fetched(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a rel="nofollow" href="/p">P</a><a href="/about">About</a>'),
                "/about": Page(body='<a href="/p">P</a>'),
                "/p": Page(body="<p>P</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/p")) == [("fetched", None, "hyperlink")]
