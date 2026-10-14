"""The titles Rules (040-add-rules, rules; seam 2)."""

from spider.rules.titles import TITLE_MISSING
from spider.store.issues import evaluate_rule
from spider.store.records import AffectedUrl
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace


def test_missing_title(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)

    assert evaluate_rule(crawl_file, TITLE_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]


def test_empty_title_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, title_count=1, title_1="", title_1_length=0
    )

    assert evaluate_rule(crawl_file, TITLE_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]
