"""Redirects followed hop by hop, each hop a URL row (022-add-fetch-policy, fetching; seam 3+6)."""

from pathlib import Path

import pytest

from spider.naming import SETTINGS_FILE_NAME
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site, Status, redirect_chain
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _redirect_of(crawl_file: object, url: str) -> list[tuple[int, str | None]]:
    return query(
        crawl_file,  # type: ignore[arg-type]
        "SELECT source.status_code, target.url FROM urls AS source "
        "LEFT JOIN urls AS target ON target.id = source.redirect_url_id WHERE source.url = ?",
        [url],
    )


def test_every_hop_of_a_redirect_chain_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A shop that moved its sale page twice: /a → /b → /c.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/a">Sale</a>'),
                "/a": Redirect("/b", status=301),
                "/b": Redirect("/c", status=302),
                "/c": Page(body="<title>Sale</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert (
        _redirect_of(crawl_file, server.url("/a")),
        _redirect_of(crawl_file, server.url("/b")),
        query(
            crawl_file,
            "SELECT status_code, discovered_via FROM urls WHERE url = ?",
            [server.url("/c")],
        ),
    ) == (
        [(301, server.url("/b"))],
        [(302, server.url("/c"))],
        [(200, "redirect")],
    )


def test_index_of_redirect_targets(temp_workspace: TempWorkspace) -> None:
    [item] = run_cli("schema", "urls", "--fields", "indexes").json()["items"]

    assert {
        "name": "urls_redirect_url_id",
        "columns": ["redirect_url_id"],
        "unique": False,
        "where": "redirect_url_id IS NOT NULL",
    } in [
        {key: index[key] for key in ("name", "columns", "unique", "where")}
        for index in item["indexes"]
    ]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_target_is_requested_before_the_next_depth(
    temp_workspace: TempWorkspace, fixture_site: StartSite, status: int
) -> None:
    # /old moved to /new, at depth 1 like /old; /blog's article is at depth 2.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/old">Old</a> <a href="/blog">Blog</a>'),
                "/old": Redirect("/new", status=status),
                "/new": Page(body="<title>New</title>"),
                "/blog": Page(body='<a href="/blog/post">Post</a>'),
                "/blog/post": Page(body="<title>Post</title>"),
            }
        )
    )

    crawled(server.url("/"))

    paths = [request.path for request in server.requests]
    assert paths.index("/new") < paths.index("/blog/post")


def test_a_relative_location_is_resolved(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/dir/r">Moved</a>'),
                "/dir/r": Redirect("../x", status=301),
                "/x": Page(body="<title>X</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT source.redirect_location, target.url FROM urls AS source "
        "JOIN urls AS target ON target.id = source.redirect_url_id WHERE source.url = ?",
        [server.url("/dir/r")],
    ) == [("../x", server.url("/x"))]


def test_a_redirect_target_loses_the_stripped_parameters(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A campaign redirect that tags its target, on a Crawl that strips the tags.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/go">Offer</a>'),
                "/go": Redirect("/offer?utm_source=mail&id=7", status=302),
                "/offer": Page(body="<title>Offer</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--strip-params", "utm_*")

    assert _redirect_of(crawl_file, server.url("/go")) == [(302, server.url("/offer?id=7"))]


def test_a_redirect_without_location_has_no_target(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/nolocation">Go</a>'), "/nolocation": Status(302)})
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT status_code, redirect_location, redirect_url_id FROM urls WHERE url = ?",
        [server.url("/nolocation")],
    ) == [(302, None, None)]


def test_a_redirect_target_keeps_the_depth(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/moved">Moved</a>'),
                "/moved": Redirect("/new", status=301),
                "/new": Page(body="<title>New</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT crawl_depth, discovered_via FROM urls WHERE url = ?",
        [server.url("/new")],
    ) == [(1, "redirect")]


def test_a_redirect_to_an_excluded_url_is_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A "Go to account" link that redirects to the logout handler.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/go">Account</a>'),
                "/go": Redirect("/logout", status=302),
                "/logout": Page(body="<title>Signed out</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--exclude", "/logout")

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, skip_reason FROM urls WHERE url = ?",
            [server.url("/logout")],
        ),
        "/logout" in [request.path for request in server.requests],
    ) == ([("skipped", "excluded")], False)


def test_a_redirect_to_an_external_url_is_checked(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    # A partner link that the shop routes through a redirect of its own.
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(body='<a href="/out">Partner</a>'),
                "/out": Redirect("http://other.test/landing", status=301),
            }
        ),
        Site({"/landing": Page(body='<title>Partner</title><a href="/deeper">More</a>')}),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, is_internal, parsed FROM urls WHERE url = ?",
            ["http://other.test/landing"],
        ),
        query(crawl_file, "SELECT url FROM urls WHERE url = ?", ["http://other.test/deeper"]),
    ) == ([("fetched", 0, 0)], [])


def test_a_redirected_image_beyond_the_depth_limit_is_checked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # The logo moved under /img/; the old address redirects.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><img src="/logo.png">'),
                "/logo.png": Redirect("/img/logo.png", status=301),
                "/img/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "0")

    assert query(
        crawl_file,
        "SELECT fetch_state, status_code FROM urls WHERE url = ?",
        [server.url("/img/logo.png")],
    ) == [("fetched", 200)]


def test_an_image_redirected_twice_beyond_the_depth_limit_is_checked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><img src="/logo.png">'),
                "/logo.png": Redirect("/img/logo.png", status=301),
                "/img/logo.png": Redirect("/static/logo.png", status=302),
                "/static/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-depth", "0")

    assert query(
        crawl_file,
        "SELECT fetch_state FROM urls WHERE url = ?",
        [server.url("/static/logo.png")],
    ) == [("fetched",)]


def _states(crawl_file: object, *urls: str) -> list[tuple[str, str, str | None]]:
    return [
        row
        for url in urls
        for row in query(
            crawl_file,  # type: ignore[arg-type]
            "SELECT url, fetch_state, skip_reason FROM urls WHERE url = ?",
            [url],
        )
    ]


def test_the_eleventh_redirect_is_not_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # Eleven site moves, each forwarding the old address to the next one.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/r1">Offer</a>'),
                **redirect_chain("/r", 11, "/r12"),
                "/r12": Page(body="<title>Offer</title>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _states(crawl_file, server.url("/r11"), server.url("/r12")) == [
        (server.url("/r11"), "fetched", None),
        (server.url("/r12"), "skipped", "max_redirects"),
    ]


def test_a_link_to_a_url_past_the_hop_limit_queues_it_again(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # The chain ends past the limit, and a blog post two Links deeper links the offer itself.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/r1">Offer</a><a href="/blog">Blog</a>'),
                **redirect_chain("/r", 3, "/offer"),
                "/offer": Page(body="<title>Offer</title>"),
                "/blog": Page(body='<a href="/blog/post">Post</a>'),
                "/blog/post": Page(body='<a href="/offer">The offer</a>'),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--max-redirects", "2")

    assert query(
        crawl_file,
        "SELECT fetch_state, skip_reason, discovered_via, crawl_depth FROM urls WHERE url = ?",
        [server.url("/offer")],
    ) == [("fetched", None, "hyperlink", 3)]


def test_the_hop_limit_is_read_from_the_settings_file(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/r1">Offer</a>'),
                **redirect_chain("/r", 2, "/offer"),
                "/offer": Page(body="<title>Offer</title>"),
            }
        )
    )
    (temp_workspace.root / SETTINGS_FILE_NAME).write_bytes(b"[crawl]\nmax_redirects = 1\n")

    crawl_file = crawled(server.url("/"))

    assert _states(crawl_file, server.url("/offer")) == [
        (server.url("/offer"), "skipped", "max_redirects")
    ]


def _loop_flags(crawl_file: Path, *urls: str) -> list[tuple[str, int | None]]:
    return [
        row
        for url in urls
        for row in query(crawl_file, "SELECT url, in_redirect_loop FROM urls WHERE url = ?", [url])
    ]


def test_a_loop_of_two_urls_is_marked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # Two rewrite rules that undo each other: the cart sends to the login, the login back.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/loop-a">Cart</a>'),
                "/loop-a": Redirect("/loop-b", status=301),
                "/loop-b": Redirect("/loop-a", status=301),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _loop_flags(crawl_file, server.url("/loop-a"), server.url("/loop-b")) == [
        (server.url("/loop-a"), 1),
        (server.url("/loop-b"), 1),
    ]


def test_only_a_redirect_on_a_loop_is_marked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # A moved page, and an account page whose redirect sends it to itself.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/old">Old</a><a href="/account">Account</a>'),
                "/old": Redirect("/new", status=301),
                "/new": Page(body="<title>New</title>"),
                "/account": Redirect("/account", status=302),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _loop_flags(
        crawl_file, server.url("/"), server.url("/old"), server.url("/new"), server.url("/account")
    ) == [
        (server.url("/"), None),
        (server.url("/old"), 0),
        (server.url("/new"), None),
        (server.url("/account"), 1),
    ]
