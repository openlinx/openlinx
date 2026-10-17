"""The meta description Rules (040-add-rules, rules; seam 2)."""

from spider.rules.meta_descriptions import META_DESCRIPTION_MISSING
from spider.store.issues import evaluate_rule
from spider.store.records import AffectedUrl
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace


def test_missing_meta_description(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, meta_description_count=0)

    assert evaluate_rule(crawl_file, META_DESCRIPTION_MISSING) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_an_empty_meta_description_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace,
        meta_description_count=1,
        meta_description_1="",
        meta_description_1_length=0,
    )

    assert evaluate_rule(crawl_file, META_DESCRIPTION_MISSING) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]
