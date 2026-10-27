"""The titles Rules (040-add-rules, rules; seam 2)."""

from dataclasses import fields
from typing import Any

import pytest

from spider.rules.headings import H1_MISSING
from spider.rules.meta_descriptions import META_DESCRIPTION_MISSING
from spider.rules.registry import RULES
from spider.rules.titles import TITLE_DUPLICATE, TITLE_MISSING, TITLE_TOO_LONG
from spider.store.issues import read_affected_urls
from spider.store.page_records import PageRow
from spider.store.records import AffectedUrl
from tests.support.crawls import query
from tests.support.page_data import page_data
from tests.support.rules import crawl_with_page, crawl_with_pages
from tests.support.workspace import TempWorkspace

UNTITLED = page_data("<h1>Sale</h1><p>Everything half price this week.</p>")
SHOES_TITLE = "Waterproof trail running shoes for wet and rocky ground"


def titled(title: str) -> dict[str, Any]:
    return page_data(f"<title>{title}</title><h1>Sale</h1>")


def test_missing_title(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, **UNTITLED)

    assert read_affected_urls(crawl_file, TITLE_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_empty_title_counts_as_missing(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, **titled(""))

    assert read_affected_urls(crawl_file, TITLE_MISSING.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_a_failed_extractor_raises_no_issue_for_its_missing_columns(
    temp_workspace: TempWorkspace,
) -> None:
    # The Page stays among the analysed Pages: a column that an extractor filled still fires.
    filled, filled_id = crawl_with_page(temp_workspace, parse_error="extractor_error", **UNTITLED)
    missing, _ = crawl_with_page(temp_workspace, parse_error="extractor_error")

    assert (
        read_affected_urls(filled, TITLE_MISSING.id, RULES),
        read_affected_urls(missing, TITLE_MISSING.id, RULES),
        read_affected_urls(missing, H1_MISSING.id, RULES),
        read_affected_urls(missing, META_DESCRIPTION_MISSING.id, RULES),
    ) == ([AffectedUrl(url_id=filled_id, detail=None)], [], [], [])


def test_a_page_that_was_not_parsed_is_not_analysed(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, parse_error="parse_timeout")

    assert (
        query(crawl_file, "SELECT url_id FROM analysed_pages"),
        read_affected_urls(crawl_file, TITLE_MISSING.id, RULES),
    ) == ([], [])


def test_title_too_long_by_characters(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_page(temp_workspace, **titled(f"{SHOES_TITLE} | Run"))

    assert read_affected_urls(crawl_file, TITLE_TOO_LONG.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"length": 61})
    ]


def test_title_at_the_limit(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(temp_workspace, **titled(f"{SHOES_TITLE} | Up"))

    assert read_affected_urls(crawl_file, TITLE_TOO_LONG.id, RULES) == []


def test_raised_title_limit(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_page(
        temp_workspace,
        thresholds={"title-too-long": {"max_chars": 70}},
        **titled(f"{SHOES_TITLE} | Trailco"),
    )
    [(stored_sql,)] = query(
        crawl_file, "SELECT reproduce_sql FROM rules WHERE id = 'title-too-long'"
    )

    # The file's own query, run alone, agrees: it binds no threshold.
    assert (
        read_affected_urls(crawl_file, TITLE_TOO_LONG.id, RULES),
        query(crawl_file, stored_sql),
    ) == ([], [])


def test_duplicate_titles_among_indexable_pages(temp_workspace: TempWorkspace) -> None:
    crawl_file, ids = crawl_with_pages(temp_workspace, titled(SHOES_TITLE), titled(SHOES_TITLE))
    detail = {"title_1": SHOES_TITLE, "pages": 2}

    assert read_affected_urls(crawl_file, TITLE_DUPLICATE.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=detail) for url_id in ids
    ]


# Once PageRow has the field, the test runs, and fails until indexable_pages leaves the
# non-indexable Pages out.
@pytest.mark.xfail(
    "indexability" not in {field.name for field in fields(PageRow)},
    reason="pages has no Indexability yet",
    strict=True,
)
def test_non_indexable_pages_are_not_compared(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_pages(
        temp_workspace,
        {**titled(SHOES_TITLE), "indexability": "indexable"},
        {**titled(SHOES_TITLE), "indexability": "non_indexable", "indexability_status": "noindex"},
    )

    assert read_affected_urls(crawl_file, TITLE_DUPLICATE.id, RULES) == []
