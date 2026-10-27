"""The headings Rules (040-add-rules, rules; seam 2)."""

from spider.rules.headings import H1_MISSING
from spider.rules.registry import RULES
from spider.store.issues import read_affected_urls
from spider.store.records import AffectedUrl
from tests.support.page_data import page_data
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace


def test_missing_h1(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace,
        **page_data("<title>Sale</title><h2>This week</h2><p>Everything half price.</p>"),
    )

    assert read_affected_urls(crawl_file, H1_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_an_empty_h1_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    # A heading whose only content is an image without alt text has no text.
    crawl_file, url_id = crawl_with_page(
        temp_workspace, **page_data('<title>Sale</title><h1><img src="/logo.png"></h1>')
    )

    assert read_affected_urls(crawl_file, H1_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]
