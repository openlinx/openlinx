"""A Seed's Redirect Chain and the Scope (022-add-fetch-policy, fetching; seam 3+6)."""

import json
from pathlib import Path

from spider.services.crawling import CrawlResult
from tests.fixture_site.hosts import StartNamedHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site
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
            if warning.code == "seed_redirected_out_of_scope"
        ],
        "other.test" in _scope_hosts(result.crawl_file),
    ) == ([True], False)


def _warned(result: CrawlResult, code: str) -> list[str]:
    return [warning.hint or "" for warning in result.warnings if warning.code == code]


def test_a_seed_chain_cut_by_the_hop_limit_off_its_site_is_reported(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The shop's domain forwards to its new owner, and the user follows no redirect at all.
    hosts = fixture_named_hosts(
        {
            "site.test": Site({"/": Redirect("http://other.test/", status=301)}),
            "other.test": Site({"/": Page(body="<title>New owner</title>")}),
        }
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver, max_redirects=0)

    assert (
        ["http://other.test/" in hint for hint in _warned(result, "seed_redirected_out_of_scope")],
        _internal(result.crawl_file, "http://other.test/"),
    ) == ([True], [("http://other.test/", 0, 0)])


def test_a_seed_chain_cut_by_the_url_limit_is_decided_by_its_final_scope(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # A www Seed that moved to its apex, crawled with a budget of one request.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/", status=301)}),
            "site.test": Site({"/": Page(body="<title>Shop</title>")}),
        }
    )

    result = crawl_result("http://www.site.test/", resolver=hosts.resolver, max_urls=1)

    assert (
        query(
            result.crawl_file,
            "SELECT fetch_state, is_internal FROM urls WHERE url = 'http://site.test/'",
        ),
        "site.test" in _scope_hosts(result.crawl_file),
    ) == ([("queued", 0)], False)


def test_a_section_seed_whose_chain_leaves_the_section_is_reported(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # The blog was folded into the home page, and its old address forwards there.
    server = fixture_site(
        Site(
            {
                "/blog/": Redirect("/", status=301),
                "/": Page(body='<title>Home</title><a href="/shop">Shop</a>'),
            }
        )
    )

    result = crawl_result(server.url("/blog/"), scope="subfolder")

    assert (
        [server.url("/") in hint for hint in _warned(result, "seed_redirected_out_of_scope")],
        query(result.crawl_file, "SELECT in_scope FROM urls WHERE url = ?", [server.url("/")]),
        json.loads(query(result.crawl_file, "SELECT scope FROM crawl")[0][0])["folder"],
        query(result.crawl_file, "SELECT url FROM urls WHERE url = ?", [server.url("/shop")]),
    ) == ([True], [(0,)], "/blog/", [])


def test_a_section_seed_that_moved_to_the_apex_keeps_its_section(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The blog moved from www to the apex, under the same folder.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/blog/": Redirect("http://site.test/blog/", status=301)}),
            "site.test": Site(
                {
                    "/blog/": Page(body='<a href="/blog/post">Post</a><a href="/shop">Shop</a>'),
                    "/blog/post": Page(body="<title>Post</title>"),
                }
            ),
        }
    )

    result = crawl_result("http://www.site.test/blog/", resolver=hosts.resolver, scope="subfolder")

    assert (
        query(
            result.crawl_file,
            "SELECT url, fetch_state, in_scope FROM urls WHERE url IN (?, ?) ORDER BY url",
            ["http://site.test/blog/post", "http://site.test/shop"],
        ),
        "site.test" in _scope_hosts(result.crawl_file),
    ) == (
        [("http://site.test/blog/post", "fetched", 1), ("http://site.test/shop", "fetched", 0)],
        True,
    )


def test_a_seed_blocked_by_robots_txt_at_its_chain_s_end_is_reported(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # The site moved to its apex, whose robots.txt still shuts every crawler out.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/": Redirect("http://site.test/", status=301)}),
            "site.test": Site(
                {
                    "/robots.txt": Robots("User-agent: *\nDisallow: /\n"),
                    "/": Page(body="<title>Shop</title>"),
                }
            ),
        }
    )

    result = crawl_result("http://www.site.test/", resolver=hosts.resolver)

    assert [w.code for w in result.warnings if w.code == "seed_blocked_by_robots_txt"] == [
        "seed_blocked_by_robots_txt"
    ]


def test_a_page_reached_through_an_external_redirect_is_followed(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # A partner's tracking link sends its visitors back to the shop's promotion.
    hosts = fixture_named_hosts(
        {
            "site.test": Site(
                {
                    "/": Page(body='<a href="http://other.test/go">Partner</a>'),
                    "/promo": Page(body='<a href="/deal">Deal</a>'),
                    "/deal": Page(body="<title>Deal</title>"),
                }
            ),
            "other.test": Site({"/go": Redirect("http://site.test/promo", status=302)}),
        }
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(crawl_file, "SELECT parsed FROM urls WHERE url = 'http://site.test/promo'"),
        query(crawl_file, "SELECT fetch_state FROM urls WHERE url = 'http://site.test/deal'"),
    ) == ([(1,)], [("fetched",)])


def test_a_seed_chain_that_ends_on_a_checked_url_widens_the_scope_once_it_ends(
    temp_workspace: TempWorkspace, fixture_named_hosts: StartNamedHosts
) -> None:
    # Only the shop is crawled, and it moved from www.site.test/shop/ to site.test/store/,
    # which the include pattern leaves checked, never followed.
    hosts = fixture_named_hosts(
        {
            "www.site.test": Site({"/shop/": Redirect("http://site.test/store/", status=301)}),
            "site.test": Site({"/store/": Page(body="<title>Store</title>")}),
        }
    )

    result = crawl_result("http://www.site.test/shop/", resolver=hosts.resolver, include=["/shop/"])

    assert (
        _internal(result.crawl_file, "http://site.test/store/"),
        "site.test" in _scope_hosts(result.crawl_file),
    ) == ([("http://site.test/store/", 1, 0)], True)
