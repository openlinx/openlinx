"""The headings Rules (040-add-rules, rules; seam 2)."""

from spider.rules.headings import H1_MISSING
from spider.store.records import AffectedUrl
from tests.support.rules import crawl_with_page, evaluate_rule
from tests.support.workspace import TempWorkspace


def test_missing_h1(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, h1_count=0)

    assert evaluate_rule(crawl_file, H1_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]


def test_an_empty_h1_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, h1_count=1, h1_1="", h1_1_length=0)

    assert evaluate_rule(crawl_file, H1_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]
