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


def test_words_with_apostrophes_hyphens_and_dots() -> None:
    row = page_row("<p>Don't stop \N{EM DASH} it's state-of-the-art, v2.0!</p>")

    assert row.word_count == 5


def test_a_devanagari_word_with_its_marks_is_one_word() -> None:
    # "Hindi is the official language of India": vowel signs and viramas are marks (M).
    row = page_row(
        "<p>\u0939\u093f\u0928\u094d\u0926\u0940 \u092d\u093e\u0930\u0924 \u0915\u0940 "
        "\u0930\u093e\u091c\u092d\u093e\u0937\u093e \u0939\u0948\u0964</p>"
    )

    assert row.word_count == 5


def test_an_underscore_separates_words() -> None:
    # A Python name in a tutorial's prose.
    assert page_row("<p>Call snake_case() on the name.</p>").word_count == 6
