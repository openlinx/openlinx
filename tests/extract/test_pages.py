"""Page rows (030-add-page-data, page-data; seam 3+6)."""

from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_html_response_becomes_a_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/about": Page(body="<p>About</p>")}))

    crawl_file = crawl_result(server.url("/about")).crawl_file

    assert query(crawl_file, "SELECT address FROM pages") == [(server.url("/about"),)]


def test_image_response_is_not_a_page(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/logo.png">Logo</a>'),
                "/logo.png": Page(body="PNG", content_type="image/png"),
            }
        )
    )
    logo = server.url("/logo.png")

    crawl_file = crawl_result(server.url("/")).crawl_file

    assert (
        query(crawl_file, "SELECT fetch_state, content_type FROM urls WHERE url = ?", [logo]),
        query(crawl_file, "SELECT url_id FROM pages WHERE address = ?", [logo]),
    ) == ([("fetched", "image/png")], [])


def test_external_html_response_is_not_a_page(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    hosts = fixture_hosts(
        Site(routes={"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site(routes={"/page": Page(body="<p>Page</p>")}),
    )
    other = "http://other.test/page"

    crawl_file = crawl_result("http://site.test/", resolver=hosts.resolver).crawl_file

    assert (
        query(crawl_file, "SELECT fetch_state, is_internal FROM urls WHERE url = ?", [other]),
        query(crawl_file, "SELECT url_id FROM pages WHERE address = ?", [other]),
    ) == ([("fetched", 0)], [])
