"""robots.txt over HTTP (020-add-crawl-core D6, crawling; seam 3 and 3+6)."""

from pathlib import Path

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Robots, Site, Status, redirect_chain
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.sites import NINE_PAGES
from tests.support.workspace import TempWorkspace


def test_robots_txt_is_fetched_once_per_origin(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(NINE_PAGES)

    crawled(server.url("/"))

    assert [request.path for request in server.requests if request.path == "/robots.txt"] == [
        "/robots.txt"
    ]


# /robots.txt disallows /private/, which / links to.
PRIVATE_SITE = Site(
    routes={
        "/robots.txt": Robots("User-agent: *\nDisallow: /private/\n"),
        "/": Page(body='<a href="/private/a">A</a>'),
        "/private/a": Page(body="<p>A</p>"),
    }
)


def test_a_disallowed_url_is_not_requested(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawled(server.url("/"))

    assert [request.path for request in server.requests if request.path == "/private/a"] == []


def test_a_disallowed_url_is_recorded_as_blocked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT skip_reason, blocked_by_robots_txt FROM urls WHERE url = ?",
        [server.url("/private/a")],
    ) == [("blocked_by_robots_txt", 1)]


def test_a_requested_url_is_allowed_and_a_url_skipped_before_robots_txt_is_unchecked(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"), "--exclude", "/private/")

    assert query(crawl_file, "SELECT url, blocked_by_robots_txt FROM urls ORDER BY id") == [
        (server.url("/"), 0),
        (server.url("/private/a"), None),
    ]


def test_robots_txt_is_stored_with_its_origin(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    text = "User-agent: *\nCrawl-delay: 5\nDisallow: /private/\nSitemap: {{base_url}}/sitemap.xml"
    server = fixture_site(
        Site(routes={"/robots.txt": Page(body=text, template=True), "/": Page(body="<p>/</p>")})
    )
    site = server.base_url

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT robots_state, robots_status_code, robots_txt, robots_crawl_delay_ms, "
        "robots_sitemaps, robots_fetched_at IS NOT NULL FROM origins WHERE origin = ?",
        [site],
    ) == [
        (
            "ok",
            200,
            text.replace("{{base_url}}", site),
            5000,
            f'["{site}/sitemap.xml"]',
            1,
        )
    ]


def test_a_url_that_is_not_requested_still_points_to_its_origin(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site(routes={"/robots.txt": Robots("User-agent: *\nAllow: /\n")}),
    )

    crawl_file = crawl_result(
        "http://site.test/", resolver=hosts.resolver, check_external=False
    ).crawl_file

    assert query(
        crawl_file,
        "SELECT origins.origin, robots_state, robots_fetched_at, robots_sitemaps FROM urls "
        "JOIN origins ON origins.id = urls.origin_id WHERE url = ?",
        ["http://other.test/page"],
    ) == [("http://other.test", None, None, None)]


def test_disallowed_urls_are_crawled_and_still_labelled(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"), "--ignore-robots")

    assert query(
        crawl_file,
        "SELECT fetch_state, blocked_by_robots_txt FROM urls WHERE url = ?",
        [server.url("/private/a")],
    ) == [("fetched", 1)]


def _seed_and_origin(crawl_file: Path, site: str) -> tuple[object, ...]:
    """The Seed's fetch_state and skip_reason, and its origin's robots_state."""
    ((fetch_state, skip_reason, robots_state),) = query(
        crawl_file,
        "SELECT fetch_state, skip_reason, robots_state FROM urls "
        "JOIN origins ON origins.id = urls.origin_id WHERE url = ?",
        [f"{site}/"],
    )
    return fetch_state, skip_reason, robots_state


def test_a_missing_robots_txt_allows_everything(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/robots.txt": Status(404), "/": Page(body="<p>/</p>")}))

    crawl_file = crawled(server.url("/"))

    assert _seed_and_origin(crawl_file, server.base_url) == ("fetched", None, "missing")


def test_an_unreachable_robots_txt_blocks_its_origin(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/robots.txt": Status(503), "/": Page(body="<p>/</p>")}))

    crawl_file = crawled(server.url("/"))

    assert _seed_and_origin(crawl_file, server.base_url) == (
        "skipped",
        "robots_unreachable",
        "unreachable",
    )


def test_ignore_robots_requests_the_urls_of_an_unreachable_robots_txt_unlabelled(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/robots.txt": Status(503), "/": Page(body="<p>/</p>")}))

    crawl_file = crawled(server.url("/"), "--ignore-robots")

    assert query(
        crawl_file,
        "SELECT fetch_state, blocked_by_robots_txt FROM urls WHERE url = ?",
        [server.url("/")],
    ) == [("fetched", None)]


def test_a_redirected_robots_txt_is_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Redirect("/robots-real.txt"),
                "/robots-real.txt": Robots("User-agent: *\nDisallow: /private/\n"),
                "/": Page(body='<a href="/private/a">A</a>'),
                "/private/a": Page(body="<p>A</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/private/a")]
    ) == [("blocked_by_robots_txt",)]


def _robots_state_after_redirects(fixture_site: StartSite, redirects: int) -> list[tuple[object]]:
    """The robots_state of a site whose /robots.txt reaches its rules after `redirects`."""
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Redirect("/r1"),
                **redirect_chain("/r", redirects - 1, "/robots-real.txt"),
                "/robots-real.txt": Robots("User-agent: *\nDisallow: /private/\n"),
                "/": Page(body="<p>/</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    return query(crawl_file, "SELECT robots_state FROM origins WHERE origin = ?", [server.base_url])


def test_more_than_five_robots_txt_redirects_count_as_missing(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    assert _robots_state_after_redirects(fixture_site, 6) == [("missing",)]


def test_five_robots_txt_redirects_are_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    assert _robots_state_after_redirects(fixture_site, 5) == [("ok",)]


def test_a_dead_external_domain_is_a_dns_error(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="http://nowhere.test/a">A</a>'
                    '<a href="http://nowhere.test/b">B</a>'
                )
            }
        ),
        Site(routes={}),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(
            crawl_file,
            "SELECT url, fetch_state, fetch_error, instr(fetch_error_message, 'robots.txt') > 0 "
            "FROM urls WHERE url LIKE 'http://nowhere.test/%' ORDER BY id",
        ),
        query(
            crawl_file,
            "SELECT robots_state, robots_status_code, robots_fetch_error FROM origins "
            "WHERE origin = 'http://nowhere.test'",
        ),
    ) == (
        [
            ("http://nowhere.test/a", "error", "dns_error", 1),
            ("http://nowhere.test/b", "error", "dns_error", 1),
        ],
        [("unreachable", None, "dns_error")],
    )


def test_a_url_that_the_url_limit_refuses_never_requests_robots_txt(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/x">X</a>')}),
        Site(routes={"/robots.txt": Robots("User-agent: *\nAllow: /\n")}),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver, max_urls=1).crawl_file

    assert (
        [request.path for request in hosts.other.requests],
        query(crawl_file, "SELECT robots_state FROM origins WHERE origin = 'http://other.test'"),
    ) == ([], [(None,)])


def test_a_known_verdict_records_a_disallowed_url_past_the_url_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    crawl_file = crawled(server.url("/"), "--max-urls", "1")

    assert (
        crawl_row(crawl_file)["state"],
        query(crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/private/a")]),
    ) == ("completed", [("blocked_by_robots_txt",)])


def test_the_robots_user_agent_token_selects_the_robots_txt_group_that_applies(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/robots.txt": Robots("User-agent: Googlebot\nDisallow: /g\n"),
                "/": Page(body='<a href="/g">G</a>'),
                "/g": Page(body="<p>G</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--robots-user-agent", "Googlebot")

    assert query(crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/g")]) == [
        ("blocked_by_robots_txt",)
    ]


def test_two_urls_of_an_origin_reached_at_once_request_its_robots_txt_once(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="http://other.test/a">A</a><a href="http://other.test/b">B</a>'
                )
            }
        ),
        Site(routes={"/robots.txt": Robots("User-agent: *\nAllow: /\n")}),
    )

    crawl_result("http://site.test/", resolver=hosts.resolver)

    assert [request.path for request in hosts.other.requests if request.path == "/robots.txt"] == [
        "/robots.txt"
    ]


def test_a_blocked_url_that_is_not_the_seed_raises_no_seed_warning(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(PRIVATE_SITE)

    result = crawl_result(server.url("/"))

    assert [
        warning.code for warning in result.warnings if warning.code == "seed_blocked_by_robots_txt"
    ] == []


def test_an_unreachable_robots_txt_of_an_external_origin_raises_no_warning(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/a">A</a>')}),
        Site(routes={"/robots.txt": Status(503)}),
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver)

    assert [
        warning.code for warning in result.warnings if warning.code == "robots_unreachable"
    ] == []
