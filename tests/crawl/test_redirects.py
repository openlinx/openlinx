"""Redirects followed hop by hop, each hop a URL row (022-add-fetch-policy, fetching; seam 3+6)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawled
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
