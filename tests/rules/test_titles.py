"""The titles Rules (040-add-rules, rules; seam 2)."""

import pytest

from spider.rules.headings import H1_MISSING
from spider.rules.titles import TITLE_DUPLICATE, TITLE_MISSING, TITLE_TOO_LONG
from spider.store.issues import evaluate_rule
from spider.store.records import AffectedUrl
from tests.support.crawls import query
from tests.support.rules import crawl_with_page, crawl_with_pages
from tests.support.workspace import TempWorkspace


def test_missing_title(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, title_count=0)

    assert evaluate_rule(crawl_file, TITLE_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]


def test_empty_title_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, title_count=1, title_1="", title_1_length=0
    )

    assert evaluate_rule(crawl_file, TITLE_MISSING) == [AffectedUrl(url_id=url_id, detail=None)]


def test_a_failed_extractor_raises_no_issue_for_its_missing_columns(
    temp_workspace: TempWorkspace,
) -> None:
    # The Page stays among the analysed Pages: a column that an extractor filled still fires.
    filled, filled_id = crawl_with_page(
        temp_workspace, parse_error="extractor_error", title_count=0
    )
    missing, _ = crawl_with_page(temp_workspace, parse_error="extractor_error")

    assert (
        evaluate_rule(filled, TITLE_MISSING),
        evaluate_rule(missing, TITLE_MISSING),
        evaluate_rule(missing, H1_MISSING),
    ) == ([AffectedUrl(url_id=filled_id, detail=None)], [], [])


def test_a_page_that_was_not_parsed_is_not_analysed(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, parse_error="parse_timeout", title_count=0)

    assert (
        query(crawl_file, "SELECT url_id FROM analysed_pages"),
        evaluate_rule(crawl_file, TITLE_MISSING),
    ) == ([], [])


def test_title_too_long_by_characters(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(
        temp_workspace, title_count=1, title_1="x" * 61, title_1_length=61
    )

    assert evaluate_rule(crawl_file, TITLE_TOO_LONG) == [
        AffectedUrl(url_id=url_id, detail={"length": 61})
    ]


def test_title_at_the_limit(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(
        temp_workspace, title_count=1, title_1="x" * 60, title_1_length=60
    )

    assert evaluate_rule(crawl_file, TITLE_TOO_LONG) == []


def test_raised_title_limit(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(
        temp_workspace,
        thresholds={"title-too-long": {"max_chars": 70}},
        title_count=1,
        title_1="x" * 65,
        title_1_length=65,
    )
    [(stored_sql,)] = query(
        crawl_file, "SELECT reproduce_sql FROM rules WHERE id = 'title-too-long'"
    )

    # The file's own query, run alone, agrees: it binds no threshold.
    assert (evaluate_rule(crawl_file, TITLE_TOO_LONG), query(crawl_file, stored_sql)) == ([], [])


SHOES = {"title_count": 1, "title_1": "Shoes", "title_1_length": 5}


def test_duplicate_titles_among_indexable_pages(temp_workspace: TempWorkspace) -> None:
    crawl_file, ids = crawl_with_pages(temp_workspace, SHOES, SHOES)
    detail = {"title_1": "Shoes", "pages": 2}

    assert sorted(evaluate_rule(crawl_file, TITLE_DUPLICATE), key=lambda url: url.url_id) == [
        AffectedUrl(url_id=url_id, detail=detail) for url_id in ids
    ]


# Fails with a TypeError until PageRow has the Indexability columns; with them it fails on its
# assertion, which the mark does not allow, until indexable_pages leaves non-indexable Pages out.
@pytest.mark.xfail(raises=TypeError, strict=True, reason="pages has no Indexability yet")
def test_non_indexable_pages_are_not_compared(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {**SHOES, "indexability": "indexable"},
        {**SHOES, "indexability": "non_indexable", "indexability_status": "noindex"},
    )

    assert evaluate_rule(crawl_file, TITLE_DUPLICATE) == []
