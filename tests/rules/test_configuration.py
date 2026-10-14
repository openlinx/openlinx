"""Rule configuration fixed per Crawl (040-add-rules D6, D14; seam 3+6)."""

import json

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

HOME_PAGE = Site({"/": Page(body="<title>Home</title>")})


def test_crawl_records_the_thresholds_it_used(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(HOME_PAGE)
    (temp_workspace.root / "spider.toml").write_bytes(b"[rules.title-too-long]\nmax_chars = 70\n")

    [(thresholds,)] = query(
        crawled(server.url("/")), "SELECT thresholds FROM rules WHERE id = 'title-too-long'"
    )

    assert json.loads(thresholds) == {"max_chars": 70}
