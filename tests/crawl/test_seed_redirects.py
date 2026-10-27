"""A Seed's Redirect Chain and the Scope (022-add-fetch-policy, fetching; seam 3+6)."""

import json
from pathlib import Path

from tests.fixture_site.hosts import StartNamedHosts
from tests.fixture_site.routes import Page, Redirect, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _internal(crawl_file: Path, *urls: str) -> list[tuple[str, int, int]]:
    return [
        row
        for url in urls
        for row in query(
            crawl_file,
            "SELECT url, is_internal, in_scope FROM urls WHERE url = ?",
            [url],
        )
    ]


def _scope_hosts(crawl_file: Path) -> list[str]:
    [(scope,)] = query(crawl_file, "SELECT scope FROM crawl")
    hosts: list[str] = json.loads(scope)["hosts"]
    return hosts


def test_a_redirect_to_the_apex_host_stays_inside_the_scope(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The site moved from www to its apex; the old address still gets the links.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/", status=301)}),
            "site.test": Site(
                {
                    "/": Page(body='<title>Shop</title><a href="/a">Shoes</a>'),
                    "/a": Page(body="<title>Shoes</title>"),
                }
            ),
        }
    )

    crawl_file = crawl_result("http://www.site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, is_internal FROM urls WHERE url = 'http://site.test/a'",
        ),
        "site.test" in _scope_hosts(crawl_file),
    ) == ([("fetched", 1)], True)


def test_every_hop_of_a_seed_chain_that_widens_the_scope_is_internal(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/old", status=301)}),
            "site.test": Site(
                {
                    "/old": Redirect("/", status=301),
                    "/": Page(body="<title>Shop</title>"),
                }
            ),
        }
    )

    crawl_file = crawl_result("http://www.site.test/", resolver=hosts.resolver).crawl_file

    assert _internal(crawl_file, "http://site.test/old", "http://site.test/") == [
        ("http://site.test/old", 1, 1),
        ("http://site.test/", 1, 1),
    ]


def test_a_seed_chain_that_ends_off_its_site_widens_nothing(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The shop's domain now forwards to a parking page on another domain.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/old", status=301)}),
            "site.test": Site({"/old": Redirect("http://other.test/", status=301)}),
            "other.test": Site({"/": Page(body="<title>Domain for sale</title>")}),
        }
    )

    crawl_file = crawl_result("http://www.site.test/", resolver=hosts.resolver).crawl_file

    assert (
        _internal(crawl_file, "http://site.test/old", "http://other.test/"),
        "site.test" in _scope_hosts(crawl_file),
    ) == ([("http://site.test/old", 0, 0), ("http://other.test/", 0, 0)], False)


def test_a_www_seed_that_redirects_on_its_host_is_checked_on_its_final_page(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The www home page moved to /home, whose canonical names the apex as the site.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site(
                {
                    "/": Redirect("/home", status=301),
                    "/home": Page(
                        body='<link rel="canonical" href="http://site.test/"><title>Shop</title>'
                    ),
                }
            ),
            "site.test": Site({"/": Page(body="<title>Shop</title>")}),
        }
    )

    result = crawl_result("http://www.site.test/", resolver=hosts.resolver)

    assert [
        "http://site.test/" in (warning.hint or "")
        for warning in result.warnings
        if warning.code == "seed_base_mismatch"
    ] == [True]


def test_a_redirect_to_another_site_is_reported(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The shop's domain now forwards to the company that bought it.
    hosts = fixture_named_hosts(
        {
            "site.test": Site({"/": Redirect("http://other.test/", status=301)}),
            "other.test": Site({"/": Page(body="<title>New owner</title>")}),
        }
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver)

    assert (
        [
            "http://other.test/" in (warning.hint or "")
            for warning in result.warnings
            if warning.code == "seed_redirected_off_site"
        ],
        "other.test" in _scope_hosts(result.crawl_file),
    ) == ([True], False)


def test_a_blog_seed_that_moved_to_the_apex_widens_the_scope_once_its_chain_ends(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The blog moved from www.site.test/blog/ to site.test/news/, outside the Seed's folder.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/blog/": Redirect("http://site.test/news/", status=301)}),
            "site.test": Site({"/news/": Page(body="<title>News</title>")}),
        }
    )

    result = crawl_result("http://www.site.test/blog/", resolver=hosts.resolver, scope="subfolder")

    assert (
        query(
            result.crawl_file,
            "SELECT fetch_state, is_internal, in_scope FROM urls WHERE url = ?",
            ["http://site.test/news/"],
        ),
        "site.test" in _scope_hosts(result.crawl_file),
    ) == ([("fetched", 1, 0)], True)
