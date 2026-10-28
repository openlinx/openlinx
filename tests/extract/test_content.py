"""The Content Area and its counts (030-add-page-data, page-data; seam 4)."""

from spider.extract.content import ContentArea
from tests.support.page_data import FIXTURE_A, page_row


def test_default_content_area_leaves_out_navigation() -> None:
    assert page_row(FIXTURE_A).word_count == 7


def test_empty_exclude_list_counts_everything() -> None:
    assert page_row(FIXTURE_A, content_area=ContentArea(exclude=())).word_count == 13


def test_include_selector_limits_the_content_area() -> None:
    assert page_row(FIXTURE_A, content_area=ContentArea(include=("p",))).word_count == 6


def test_an_include_inside_another_is_read_once() -> None:
    # An article inside a main: the article's words are not counted twice.
    html = "<main><p>One two</p><article><p>Three</p></article></main><aside>Four</aside>"
    area = ContentArea(include=("main", "article", "main"))

    assert page_row(html, content_area=area).word_count == 3
