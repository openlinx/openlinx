"""The Content Area and its counts (030-add-page-data, page-data; seam 4)."""

import unicodedata

from spider.extract.content import ContentArea
from spider.extract.unicode_scripts import UNICODE_VERSION
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


def test_each_ideograph_and_kana_is_a_word() -> None:
    assert page_row("<p>\u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8</p>").word_count == 8


def test_the_prolonged_sound_mark_is_a_word_of_its_own() -> None:
    # "Card", in katakana: the mark is Common in Scripts.txt and a letter (Lm).
    assert page_row("<p>\u30ab\u30fc\u30c9</p>").word_count == 3


def test_the_script_table_is_of_the_unicode_version_python_has() -> None:
    assert unicodedata.unidata_version == UNICODE_VERSION


def test_blocks_end_sentences() -> None:
    row = page_row("<body><h1>Welcome</h1><p>This is it. Really! Yes</p></body>")

    assert row.sentence_count == 4


def test_a_terminator_inside_a_word_ends_no_sentence() -> None:
    # As release notes write them: a version and a decimal end no sentence, and an ellipsis
    # before a space ends one.
    row = page_row("<p>Version 2.0 is out\u2026 and 3.5 follows! See the notes.</p>")

    assert row.sentence_count == 3


def test_text_ratio_of_a_small_document() -> None:
    row = page_row("<html><body><p>Hello world</p></body></html>")

    assert row.text_ratio_pct == 25.0


def test_the_text_ratio_is_rounded_half_up() -> None:
    # 100 x 1 / 32 is 3.125 exactly; rounding the float would give 3.12.
    assert page_row("<!doctype html><title></title>a\n").text_ratio_pct == 3.13


def test_an_empty_document_has_no_text_ratio() -> None:
    assert page_row("").text_ratio_pct is None


def test_counts_for_fixture_a() -> None:
    row = page_row(FIXTURE_A)

    assert (row.sentence_count, row.average_words_per_sentence) == (3, 2.33)


def test_the_average_is_rounded_half_up() -> None:
    # 9 words in 8 sentences is 1.125 exactly; rounding the float would give 1.12.
    row = page_row("<p>Yes. No. Maybe. Go. Stop. Wait. Run. Hi there.</p>")

    assert row.average_words_per_sentence == 1.13


def test_a_page_without_sentences_has_no_average() -> None:
    row = page_row("<p>\N{EM DASH}</p>")

    assert (row.sentence_count, row.average_words_per_sentence) == (0, None)
