"""Which Links the Crawl follows, over HTTP (020-add-crawl-core D5, crawling; seam 3+6)."""

from pathlib import Path

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _state(crawl_file: Path, url: str) -> list[tuple[object, ...]]:
    return query(
        crawl_file, "SELECT fetch_state, skip_reason, discovered_via FROM urls WHERE url = ?", [url]
    )


def test_a_meta_refresh_target_is_followed(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body='<a href="/old">Old</a>'),
                "/old": Page(body='<meta http-equiv="refresh" content="0; url=/new">'),
                "/new": Page(body="<p>New</p>"),
            }
        )
    )

    crawl_file = crawled(server.url("/"))

    assert _state(crawl_file, server.url("/new")) == [("fetched", None, "meta_refresh")]
