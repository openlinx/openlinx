"""The skips decided at dispatch (020-add-crawl-core D5, crawling; seam 3+6)."""

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_an_excluded_url_beyond_the_depth_limit_is_excluded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/a">A</a>'),
                "/a": Page(body='<a href="/logout">Out</a>'),
            }
        )
    )

    crawl_file = crawl_result(server.url("/"), max_depth=1, exclude=["/logout$"]).crawl_file

    assert query(
        crawl_file, "SELECT skip_reason FROM urls WHERE url = ?", [server.url("/logout")]
    ) == [("excluded",)]


def test_an_excluded_url_requests_no_robots_txt(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/logout">Out</a>')}),
        Site(routes={"/logout": Page(body="<p>Bye</p>")}),
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver, exclude=["/logout$"])

    assert (
        hosts.other.requests,
        query(
            result.crawl_file, "SELECT skip_reason FROM urls WHERE url = 'http://other.test/logout'"
        ),
    ) == ((), [("excluded",)])
