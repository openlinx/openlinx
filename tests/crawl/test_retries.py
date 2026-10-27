"""Retries with backoff (022-add-fetch-policy, fetching; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site, Status
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def test_a_temporary_503_is_retried(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    # A shop whose application server restarts: one 503, then the page.
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Shop</title><a href="/flaky">Sale</a>'),
                "/flaky": Responses((Status(503), Page(body="<title>Sale</title>"))),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert query(
        crawl_file,
        "SELECT status_code, attempt_count FROM urls WHERE url = ?",
        [server.url("/flaky")],
    ) == [(200, 2)]
