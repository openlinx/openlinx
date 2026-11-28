"""Verify Rule measurements after real Page extractor failures."""

from dataclasses import replace
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.engine.hooks import Hooks
from openlinx.crawl.pages.preparation import Extractor, PageInput, extractor
from openlinx.extract.content_area import ContentArea
from openlinx.extract.page_data import PAGE_DATA, PageData, extract_page_data
from openlinx.extract.page_links import PAGE_LINKS, PageLinks, extract_page_links
from openlinx.rules.headings import H1_MISSING
from openlinx.rules.titles import TITLE_MISSING
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _fail_page_data_for_unmeasured(
    tree: LexborHTMLParser, page: PageInput, config: ContentArea
) -> PageData:
    if page.url.endswith("/unmeasured"):
        raise RuntimeError("Page extractor bug")
    return extract_page_data(tree, page, config)


def _fail_page_links_for_measured_pages(
    tree: LexborHTMLParser, page: PageInput, config: None
) -> PageLinks:
    if page.url.endswith(("/title-missing", "/h1-missing")):
        raise RuntimeError("Link extractor bug")
    return extract_page_links(tree, page, config)


def _hooks_with_replacements(
    defaults: Hooks, replacements: dict[str, Extractor[Any, Any]]
) -> Hooks:
    return replace(
        defaults,
        extractors=tuple(replacements.get(built.name, built) for built in defaults.extractors),
    )


def test_a_failed_extractor_raises_no_issue_for_its_missing_columns(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        "<title>Home</title><h1>Home</h1>"
                        '<a href="/unmeasured">Unmeasured</a>'
                        '<a href="/title-missing">Missing title</a>'
                        '<a href="/h1-missing">Missing H1</a>'
                    )
                ),
                "/unmeasured": Page(body="<title>Measured</title><h1>Measured</h1>"),
                "/title-missing": Page(body="<h1>Measured heading</h1>"),
                "/h1-missing": Page(body="<title>Measured title</title>"),
            }
        )
    )
    defaults = default_hooks()
    page_data = next(built for built in defaults.extractors if built.name == PAGE_DATA.name)
    page_links = next(built for built in defaults.extractors if built.name == PAGE_LINKS.name)
    hooks = _hooks_with_replacements(
        defaults,
        {
            PAGE_DATA.name: extractor(
                PAGE_DATA.name, _fail_page_data_for_unmeasured, page_data.config
            ),
            PAGE_LINKS.name: extractor(
                PAGE_LINKS.name, _fail_page_links_for_measured_pages, page_links.config
            ),
        },
    )

    crawl_file = crawl_result(server.url("/"), hooks).crawl_file
    rows = query(
        crawl_file,
        "SELECT urls.url, urls.id, urls.parsed, urls.parse_error, pages.title_count, "
        "pages.title_1, pages.title_1_length, pages.h1_count, pages.h1_1, pages.h1_1_length "
        "FROM urls JOIN pages ON pages.url_id = urls.id WHERE urls.url IN (?, ?, ?) "
        "ORDER BY urls.url",
        (server.url("/unmeasured"), server.url("/title-missing"), server.url("/h1-missing")),
    )
    by_url = {row[0]: row for row in rows}
    assert {url: row[2:] for url, row in by_url.items()} == {
        server.url("/h1-missing"): (
            1,
            "extractor_error",
            1,
            "Measured title",
            14,
            0,
            None,
            None,
        ),
        server.url("/title-missing"): (
            1,
            "extractor_error",
            0,
            None,
            None,
            1,
            "Measured heading",
            16,
        ),
        server.url("/unmeasured"): (
            1,
            "extractor_error",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    }

    assert evaluate_rule(crawl_file, TITLE_MISSING) == [
        AffectedUrl(url_id=by_url[server.url("/title-missing")][1], detail=None)
    ]
    assert evaluate_rule(crawl_file, H1_MISSING) == [
        AffectedUrl(url_id=by_url[server.url("/h1-missing")][1], detail=None)
    ]
