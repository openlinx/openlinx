"""The titles Rules (040-add-rules, rules; seam 2)."""

from spider.rules.headings import H1_MISSING
from spider.rules.titles import TITLE_MISSING
from spider.store.issues import evaluate_rule
from spider.store.records import AffectedUrl
from tests.support.crawls import query
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
