"""The meta description Rules (040-add-rules, rules; seam 2)."""

from spider.rules.meta_descriptions import META_DESCRIPTION_MISSING
from spider.rules.registry import RULES
from spider.store.issues import read_affected_urls
from spider.store.records import AffectedUrl
from tests.support.page_data import page_data
from tests.support.rules import crawl_with_page
from tests.support.workspace import TempWorkspace


def test_missing_meta_description(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, **page_data('<title>Sale</title><meta name="robots" content="index">')
    )

    assert read_affected_urls(crawl_file, META_DESCRIPTION_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_an_empty_meta_description_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, **page_data('<title>Sale</title><meta name="description" content="">')
    )

    assert read_affected_urls(crawl_file, META_DESCRIPTION_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]
