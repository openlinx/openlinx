"""Which Links the Crawl follows (020-add-crawl-core D5, crawling; seams 3, 4 and 6)."""

from pathlib import Path
from typing import get_args

import pytest

from spider.crawl.following import requests_target
from spider.store.records import LinkType
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


def test_nofollow_links_are_followed_on_request(
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

    crawl_file = crawled(server.url("/"), "--follow-nofollow")

    assert _state(crawl_file, server.url("/private")) == [("fetched", None, "hyperlink")]


def test_an_x_robots_tag_nofollow_applies_to_every_hyperlink(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/x">X</a>', headers=[("X-Robots-Tag", "nofollow")]),
                "/x": Page(body="<p>X</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/x")) == [("skipped", "nofollow", "hyperlink")]


def test_an_excluded_url_that_only_unfollowed_links_reach_is_recorded_as_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<a rel="nofollow" href="/private">P</a><link rel="amphtml" href="/amp">'
                ),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--exclude", "/private$", "--exclude", "/amp$")

    assert (
        _state(crawl_file, server.url("/private")),
        _state(crawl_file, server.url("/amp")),
    ) == (
        [("skipped", "nofollow", "hyperlink")],
        [("skipped", "link_type_not_followed", "amphtml")],
    )


def test_the_robots_user_agent_token_selects_the_x_robots_tag_that_applies(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(
                    body='<a href="/x">X</a>', headers=[("X-Robots-Tag", "googlebot: nofollow")]
                ),
                "/x": Page(body="<p>X</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--robots-user-agent", "Googlebot")

    assert _state(crawl_file, server.url("/x")) == [("skipped", "nofollow", "hyperlink")]


# The spec's Link type table; a sitemap's types come from no Page.
_REQUESTED_BY_TYPE: dict[str, bool] = {
    **dict.fromkeys(
        ["hyperlink", "canonical", "pagination", "hreflang", "iframe", "meta_refresh"], True
    ),
    **dict.fromkeys(["http_refresh", "image", "css", "javascript", "video", "audio"], True),
    "media": True,
    **dict.fromkeys(["amphtml", "mobile_alternate", "misc", "xml_sitemap"], False),
    **dict.fromkeys(["sitemap_hreflang", "javascript_redirect"], False),
}


def test_each_link_type_requests_its_target_or_not() -> None:
    assert {
        link_type: requests_target(link_type, False, page_nofollow=False, follow_nofollow=False)
        for link_type in get_args(LinkType.__value__)
    } == _REQUESTED_BY_TYPE


@pytest.mark.parametrize(
    ("link_type", "nofollow", "page_nofollow", "follow_nofollow", "requested"),
    [
        ("hyperlink", True, False, False, False),
        ("hyperlink", False, True, False, False),
        ("hyperlink", True, True, True, True),
        ("hyperlink", True, False, True, True),
        ("hyperlink", False, True, True, True),
        # nofollow is a hyperlink's alone: a canonical or an image is requested anyway.
        ("canonical", True, True, False, True),
        ("image", True, True, False, True),
        # --follow-nofollow lifts nofollow, not the Link type table.
        ("amphtml", False, False, True, False),
    ],
)
def test_nofollow_keeps_a_hyperlink_from_requesting_its_target(
    link_type: LinkType, nofollow: bool, page_nofollow: bool, follow_nofollow: bool, requested: bool
) -> None:
    assert (
        requests_target(
            link_type, nofollow, page_nofollow=page_nofollow, follow_nofollow=follow_nofollow
        )
        == requested
    )
