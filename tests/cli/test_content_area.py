"""The [content_area] settings at the CLI (030-add-page-data D13, page-data; seam 1)."""

import json

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawled
from tests.support.crawls import crawl_row, query
from tests.support.page_data import FIXTURE_A
from tests.support.workspace import TempWorkspace


def test_invalid_selector_stops_the_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body=FIXTURE_A)}))
    (temp_workspace.root / "spider.toml").write_bytes(b'[content_area]\nexclude = ["nav["]\n')

    result = run_cli("crawl", server.url("/"))

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
        server.requests,
    ) == (3, [("settings_invalid", "content_area.exclude")], ())


def test_a_crawl_records_its_content_area(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body=FIXTURE_A)}))
    (temp_workspace.root / "spider.toml").write_bytes(
        b'[content_area]\ninclude = ["main", "article"]\nexclude = []\n'
    )

    config = json.loads(crawl_row(crawled(server.url("/")))["config"])

    assert config["content_area"] == {"include": ["main", "article"], "exclude": []}


def test_the_content_area_of_spider_toml_reaches_the_page_extractor(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body=FIXTURE_A)}))
    (temp_workspace.root / "spider.toml").write_bytes(b"[content_area]\nexclude = []\n")

    crawl_file = crawled(server.url("/"))

    assert query(crawl_file, "SELECT word_count FROM pages") == [(13,)]
