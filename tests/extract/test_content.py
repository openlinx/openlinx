"""Verify Content Area selection and text metrics through pure extraction."""

import subprocess

import pytest

from openlinx.extract.content_area import ContentArea
from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.page_data import FIXTURE_A, page_row
from tests.support.processes import python_command


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


_HTML_WITH_HEAD = "<html><head><title>Hello</title></head><body><p>world</p></body></html>"


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        pytest.param(
            ("title",),
            (1, 1, 1.0, "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969"),
            id="title",
        ),
        pytest.param(
            ("head",),
            (1, 1, 1.0, "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969"),
            id="head",
        ),
        pytest.param(
            ("html",),
            (2, 2, 1.0, "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"),
            id="html",
        ),
        pytest.param(
            ("p", "title", "title"),
            (2, 2, 1.0, "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"),
            id="document-order-and-duplicates",
        ),
        pytest.param(
            ("p", "title", "html", "head", "html"),
            (2, 2, 1.0, "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"),
            id="outermost-roots",
        ),
    ],
)
def test_explicit_content_area_roots_can_be_outside_body(
    include: tuple[str, ...], expected: tuple[int, int, float | None, str | None]
) -> None:
    row = page_row(_HTML_WITH_HEAD, content_area=ContentArea(include=include))

    assert (
        row.word_count,
        row.sentence_count,
        row.average_words_per_sentence,
        row.content_hash,
        row.title_1,
        row.text_ratio_pct,
    ) == (*expected, "Hello", 7.04)


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        pytest.param(
            ContentArea(),
            (1, 1, 1.0, "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"),
            id="default-body",
        ),
        pytest.param(
            ContentArea(include=("title",), exclude=("head",)),
            (0, 0, None, None),
            id="excluded-ancestor",
        ),
        pytest.param(
            ContentArea(include=("title",), exclude=("title",)),
            (0, 0, None, None),
            id="excluded-root",
        ),
        pytest.param(
            ContentArea(include=("html",), exclude=("head",)),
            (1, 1, 1.0, "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"),
            id="excluded-head",
        ),
        pytest.param(
            ContentArea(include=("html",), exclude=("html",)),
            (0, 0, None, None),
            id="excluded-container",
        ),
        pytest.param(
            ContentArea(exclude=("body",)), (0, 0, None, None), id="excluded-default-body"
        ),
        pytest.param(
            ContentArea(exclude=("html",)), (0, 0, None, None), id="excluded-default-ancestor"
        ),
        pytest.param(ContentArea(include=(".missing",)), (0, 0, None, None), id="no-match"),
    ],
)
def test_content_area_roots_keep_exclusions_and_default_body(
    area: ContentArea, expected: tuple[int, int, float | None, str | None]
) -> None:
    row = page_row(_HTML_WITH_HEAD, content_area=area)

    assert (
        row.word_count,
        row.sentence_count,
        row.average_words_per_sentence,
        row.content_hash,
        row.title_1,
        row.text_ratio_pct,
    ) == (*expected, "Hello", 7.04)


@pytest.mark.parametrize(
    ("include", "sentences", "average"),
    [
        pytest.param(("main", "span", "main"), 1, 2.0, id="outermost-root"),
        pytest.param(("span",), 2, 1.0, id="sibling-roots"),
    ],
)
def test_only_outermost_content_area_roots_start_blocks(
    include: tuple[str, ...], sentences: int, average: float
) -> None:
    row = page_row(
        "<main><span>Hello</span> <span>world</span></main>",
        content_area=ContentArea(include=include, exclude=()),
    )

    assert (
        row.word_count,
        row.sentence_count,
        row.average_words_per_sentence,
        row.content_hash,
    ) == (2, sentences, average, "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c")


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        pytest.param(
            ("head",),
            (1, 1, 1.0, "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969"),
            id="head",
        ),
        pytest.param(("script",), (0, 0, None, None), id="skipped-root"),
    ],
)
def test_explicit_content_area_roots_keep_skipped_subtrees_out(
    include: tuple[str, ...], expected: tuple[int, int, float | None, str | None]
) -> None:
    row = page_row(
        "<html><head><title>Hello</title><script>extra words</script>"
        "<style>more words</style></head><body><p>world</p></body></html>",
        content_area=ContentArea(include=include),
    )

    assert (
        row.word_count,
        row.sentence_count,
        row.average_words_per_sentence,
        row.content_hash,
    ) == expected


def test_fixture_a_title_can_be_an_explicit_content_area_root() -> None:
    row = page_row(FIXTURE_A, content_area=ContentArea(include=("title",)))

    assert (row.word_count, row.content_hash) == (
        1,
        "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969",
    )


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


def test_a_mark_stays_with_the_han_or_kana_character_before_it() -> None:
    # "Guide" decomposed (NFD), as a Mac file name sends it, and Katsushika with the variation
    # selector that picks the glyph of its first ideograph.
    row = page_row("<p>ガイド 葛\U000e0100飾区</p>")

    assert row.word_count == 6


def test_a_word_of_a_script_new_in_unicode_16_counts_on_every_python() -> None:
    # A line naming the Kirat Rai script, then a word in it (Unicode 16.0, which Python 3.12
    # and 3.13 do not have yet).
    row = page_row("<p>Kirat Rai: \U00016d44\U00016d64\U00016d5d\U00016d52</p>")

    assert row.word_count == 3


def test_blocks_end_sentences() -> None:
    row = page_row("<body><h1>Welcome</h1><p>This is it. Really! Yes</p></body>")

    assert row.sentence_count == 4


def test_a_terminator_inside_a_word_ends_no_sentence() -> None:
    # As release notes write them: a version and a decimal end no sentence, and an ellipsis
    # before a space ends one.
    row = page_row("<p>Version 2.0 is out\u2026 and 3.5 follows! See the notes.</p>")

    assert row.sentence_count == 3


def test_a_terminator_before_a_unicode_space_ends_a_sentence() -> None:
    # Templates put &nbsp; after a full stop, and Japanese pages an ideographic space.
    row = page_row("<p>Free shipping.&nbsp;Order today!　Read the terms.</p>")

    assert row.sentence_count == 3


@pytest.mark.slow
def test_a_long_terminator_run_does_not_stall_page_preparation() -> None:
    # A failed boundary match must not restart at every terminator. The existing process
    # watchdog bounds a stall; this is not a comparison of machine-dependent timings.
    command = python_command(
        "-c",
        "from tests.support.page_data import page_row\n"
        "row = page_row('<p>' + '.' * 100_000 + 'x</p>')\n"
        "assert (row.word_count, row.sentence_count, row.average_words_per_sentence) "
        "== (1, 1, 1.0)",
    )
    subprocess.run(
        command.argv,
        cwd=REPO_ROOT,
        env=command.env,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=True,
    )


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


def test_declared_language_is_trimmed_not_normalised() -> None:
    assert page_row('<html lang=" en-GB "><p>Colour</p></html>').declared_language == "en-GB"


def test_a_lang_attribute_without_a_value_is_empty() -> None:
    rows = [page_row("<html lang><p>a</p></html>"), page_row("<html><p>a</p></html>")]

    assert [row.declared_language for row in rows] == ["", None]


def test_each_include_selector_is_read_on_its_own() -> None:
    # A selector pasted with a comment left open: it compiles alone, and in one list with the
    # others it would swallow them.
    area = ContentArea(include=("main /*", "p"))

    assert page_row("<main>Intro</main><p>Read this</p>", content_area=area).word_count == 3


_HELLO_WORLD = "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"


def test_hash_of_a_simple_content_area() -> None:
    assert page_row("<p>Hello   world</p>").content_hash == _HELLO_WORLD


def test_different_markup_same_text() -> None:
    assert page_row("<div><p>Hello</p><p>world</p></div>").content_hash == _HELLO_WORLD


def test_composed_and_decomposed_accents_hash_differently() -> None:
    rows = [page_row("<p>Caf&#233;</p>"), page_row("<p>Cafe&#769;</p>")]

    assert [row.content_hash for row in rows] == [
        "73473dcc12b763085904a5279d048c4d5b3b008c46f1f32443b99de04aa83a14",
        "c42cc7a1ca08364b6fd859fa50d2454730a8236290a423373cc630da77c6d711",
    ]


def test_empty_content_area_has_no_hash() -> None:
    assert page_row('<body><nav><a href="/">Home</a></nav></body>').content_hash is None
