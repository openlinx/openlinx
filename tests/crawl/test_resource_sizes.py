"""Resource sizes (022-add-fetch-policy, fetching; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.fixture_site.sites.exact import site as exact
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_an_image_s_size_is_recorded(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            root=exact.SITE.root,
            routes={
                "/": Page(body='<title>Shop</title><img src="/logo.png" alt="Shop">'),
                # A 32-pixel PNG logo of 2,048 bytes.
                "/logo.png": Page(file="logo.png", content_type="image/png"),
            },
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT status_code, size_bytes, transferred_bytes, parsed FROM urls WHERE url = ?",
        [server.url("/logo.png")],
    ) == [(200, 2048, 2048, 0)]
