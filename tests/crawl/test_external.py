"""Internal and External URLs over HTTP (020-add-crawl-core, crawling; seam 3+6)."""

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

EMPTY = Site(routes={})
LINKS_TO_OTHER = Site(routes={"/": Page(body='<a href="http://other.test/page">Other</a>')})
OTHER_PAGE = Site(routes={"/page": Page(body="<p>Page</p>")})


def test_an_external_url_is_checked(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        LINKS_TO_OTHER,
        Site(
            routes={
                "/page": Page(body='<a href="http://other.test/deeper">Deeper</a>'),
                "/deeper": Page(body="<p>Deeper</p>"),
            }
        ),
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(
            crawl_file,
            "SELECT fetch_state, parsed FROM urls WHERE url = ?",
            ["http://other.test/page"],
        ),
        query(crawl_file, "SELECT id FROM urls WHERE url = ?", ["http://other.test/deeper"]),
    ) == ([("fetched", 0)], [])


def test_each_url_records_whether_it_is_internal_and_in_scope(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="/about">About</a> <a href="/logout">Out</a> '
                    '<a href="http://www.site.test/w">W</a> <a href="http://other.test/">Other</a>'
                ),
                "/about": Page(body="<p>About</p>"),
            }
        ),
        EMPTY,
    )

    crawl_file = crawl_result(
        "http://site.test/", resolver=hosts.resolver, exclude=["/logout$"]
    ).crawl_file

    assert sorted(query(crawl_file, "SELECT url, is_internal, in_scope FROM urls")) == [
        ("http://other.test/", 0, 0),
        ("http://site.test/", 1, 1),
        ("http://site.test/about", 1, 1),
        ("http://site.test/logout", 1, 0),
        ("http://www.site.test/w", 1, 1),
    ]


def test_an_external_origin_gets_its_own_row(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(LINKS_TO_OTHER, OTHER_PAGE)

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert sorted(query(crawl_file, "SELECT origin, is_internal FROM origins")) == [
        ("http://other.test", 0),
        ("http://site.test", 1),
    ]


def test_each_url_points_to_its_origin(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(
            routes={
                "/": Page(
                    body='<a href="/about">About</a> <a href="http://other.test/page">Other</a> '
                    '<a href="http://other.test:8080/port">Port</a>'
                ),
                "/about": Page(body="<p>About</p>"),
            }
        ),
        OTHER_PAGE,
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert sorted(
        query(
            crawl_file,
            "SELECT urls.url, origins.origin, origins.host FROM urls "
            "JOIN origins ON origins.id = urls.origin_id",
        )
    ) == [
        ("http://other.test/page", "http://other.test", "other.test"),
        ("http://other.test:8080/port", "http://other.test:8080", "other.test"),
        ("http://site.test/", "http://site.test", "site.test"),
        ("http://site.test/about", "http://site.test", "site.test"),
    ]


def test_external_urls_can_be_left_unchecked(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(LINKS_TO_OTHER, OTHER_PAGE)

    crawl_result("http://site.test/", resolver=hosts.resolver, check_external=False)

    assert hosts.other.requests == ()


def test_an_unknown_host_is_a_dns_error(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://nowhere.test/">Nowhere</a>')}), EMPTY
    )

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert query(
        crawl_file,
        "SELECT fetch_state, fetch_error FROM urls WHERE url = ?",
        ["http://nowhere.test/"],
    ) == [("error", "dns_error")]


def test_dead_external_links_do_not_fail_the_crawl(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    links = "".join(f'<a href="http://nowhere.test/{n}">Gone</a>' for n in range(1, 13))
    hosts = fixture_hosts(Site(routes={"/": Page(body=links)}), EMPTY)

    # With no network wait, a network pause that counted External URLs would fail it at once.
    result = crawl_result(
        "http://site.test/", resolver=hosts.resolver, concurrency=1, network_wait=0
    )

    assert result.summary.state == "completed"
