"""The columns the Page extractor derives from the HTML (030-add-page-data, page-data; seam 4)."""

import sys
from dataclasses import fields
from types import FrameType

from hypothesis import given
from hypothesis import strategies as st

from spider.extract.text import element_text
from spider.store.page_records import PageRow
from spider.store.schema import pages
from tests.support.page_data import page_row


def test_charset_declared_in_a_meta_element() -> None:
    body = '<meta charset="windows-1251"><title>Привет</title>'.encode("cp1251")

    assert page_row(body, content_type="text/html").title_1 == "Привет"


def test_whitespace_is_collapsed_before_measuring() -> None:
    row = page_row("<title>  Hello\n   World </title>")

    assert (row.title_1, row.title_1_length) == ("Hello World", 11)


def test_a_no_break_space_stays_in_a_title() -> None:
    nbsp = "\N{NO-BREAK SPACE}"

    row = page_row(f"<title>{nbsp}a{nbsp} \t b{nbsp}</title>")

    assert (row.title_1, row.title_1_length) == (f"{nbsp}a{nbsp} b{nbsp}", 6)


def test_title_in_svg_is_ignored() -> None:
    row = page_row("<head><title>Main</title></head><body><svg><title>Icon</title></svg></body>")

    assert (row.title_count, row.title_2) == (1, None)


def test_title_in_noscript_is_ignored() -> None:
    row = page_row(
        "<head><title>Main</title></head>"
        "<body><noscript><title>Enable JavaScript</title></noscript></body>"
    )

    assert (row.title_1, row.title_count) == ("Main", 1)


def test_title_in_head_noscript_is_ignored() -> None:
    row = page_row(
        "<head><noscript><title>Enable JavaScript</title></noscript><title>Main</title></head>"
    )

    assert (row.title_1, row.title_count) == ("Main", 1)


def test_a_title_in_math_is_ignored() -> None:
    row = page_row("<title>Main</title><math><mi><title>m</title></mi></math>")

    assert (row.title_1, row.title_count) == ("Main", 1)


def test_second_title_element() -> None:
    row = page_row("<head><title>One</title><title>Two</title></head>")

    assert (row.title_count, row.title_2, row.title_2_length) == (2, "Two", 3)


def test_missing_title() -> None:
    row = page_row("<p>No title</p>")

    assert (row.title_count, row.title_1, row.title_1_length) == (0, None, None)


def test_meta_description_is_normalised() -> None:
    row = page_row('<meta name="Description" content="  Buy   shoes ">')

    assert (row.meta_description_1, row.meta_description_1_length) == ("Buy shoes", 9)


def test_a_meta_description_without_content_is_empty() -> None:
    row = page_row('<meta name=" description ">')

    assert (row.meta_description_1, row.meta_description_1_length) == ("", 0)


def test_a_meta_description_in_noscript_is_ignored() -> None:
    row = page_row(
        '<head><noscript><meta name="description" content="No script"></noscript>'
        '<meta name="description" content="Main"></head>'
    )

    assert row.meta_description_1 == "Main"


def test_multiple_meta_descriptions() -> None:
    row = page_row('<meta name="description" content="A"><meta name="description" content="B">')

    assert (
        row.meta_description_count,
        row.meta_description_2,
        row.meta_description_2_length,
    ) == (2, "B", 1)


def test_meta_keywords() -> None:
    row = page_row('<meta name="keywords" content="shoes, boots">')

    assert (row.meta_keywords_1, row.meta_keywords_1_length) == ("shoes, boots", 12)


def test_heading_text_includes_nested_elements() -> None:
    row = page_row(
        "<body><h1>Main <span>Title</span></h1><h1>Second</h1><h1>Third</h1><h2>Sub</h2></body>"
    )

    assert (
        (row.h1_1, row.h1_1_length, row.h1_2, row.h1_2_length, row.h1_count),
        (row.h2_1, row.h2_1_length, row.h2_2, row.h2_2_length, row.h2_count),
    ) == (("Main Title", 10, "Second", 6, 3), ("Sub", 3, None, None, 1))


def test_heading_text_leaves_out_scripts_and_styles() -> None:
    row = page_row("<h1>Price<script>var x = 1</script><style>b {}</style> 10</h1>")

    assert row.h1_1 == "Price 10"


def test_a_heading_in_noscript_is_ignored() -> None:
    row = page_row("<body><noscript><h1>Enable JavaScript</h1></noscript><h1>Main</h1></body>")

    assert (row.h1_1, row.h1_count) == ("Main", 1)


def test_line_break_separates_heading_words() -> None:
    assert page_row("<h1>Hello<br>World</h1>").h1_1 == "Hello World"


def test_block_elements_separate_heading_words() -> None:
    assert page_row("<h1>One<p>Two</p>Three<span>Four</span></h1>").h1_1 == "One Two ThreeFour"


def test_absent_and_empty_elements_differ() -> None:
    row = page_row("<head><title></title></head><body></body>")

    assert (row.title_1, row.title_1_length, row.h1_1) == ("", 0, None)


def test_heading_text_leaves_out_fallbacks_frames_and_pictures() -> None:
    row = page_row(
        "<h1>a<noscript>n</noscript><template>t</template><iframe>i</iframe>"
        "<svg><text>s</text></svg><math><mi>m</mi></math>b</h1>"
    )

    assert row.h1_1 == "ab"


def _text_walks(html: str) -> int:
    calls = 0

    def count(frame: FrameType, event: str, arg: object) -> None:
        nonlocal calls
        if event == "call" and frame.f_code is element_text.__code__:
            calls += 1

    sys.setprofile(count)
    try:
        page_row(html)
    finally:
        sys.setprofile(None)
    return calls


def test_headings_read_the_text_of_their_first_two_elements_only() -> None:
    # The parser nests an h1 inside a div inside an h1, so each h1 holds every later one:
    # reading the text of all of them cost their count squared. Calls are counted, not
    # timed, so the test does not depend on the machine.
    assert _text_walks("<h1><div>" * 100) == _text_walks("<h1><div>" * 10)


# Two of every element the Page extractor reads; a group that adds an HTML column adds its
# element here.
_FULL_PAGE = (
    "<title>T1</title><title>T2</title>"
    '<meta name="description" content="D1"><meta name="description" content="D2">'
    '<meta name="keywords" content="K1">'
    "<h1>A1</h1><h1>A2</h1><h2>B1</h2><h2>B2</h2>"
)
# Filled by a post-crawl pass or by a later release, so NULL on a Page that was just prepared.
_LATER = ("Derived: ", "Filled from ")


def test_a_full_page_fills_every_html_column() -> None:
    row = page_row(_FULL_PAGE)
    later = {column.name for column in pages.c if (column.comment or "").startswith(_LATER)}

    assert [
        field.name
        for field in fields(PageRow)
        if field.default is None and field.name not in later and getattr(row, field.name) is None
    ] == []


def test_a_deeply_nested_heading_needs_no_recursion() -> None:
    assert page_row("<h1>" + "<div>" * 5000 + "Deep</h1>").h1_1 == "Deep"


def test_a_heading_in_a_template_is_ignored() -> None:
    row = page_row("<template><h1>Template</h1></template><h1>Main</h1>")

    assert (row.h1_1, row.h1_count) == ("Main", 1)


# Fragments that build the documents a parser repairs: unclosed, nested in foreign content,
# commented out, NUL and stray markup, with each element the extractor reads or walks.
_FRAGMENTS = st.sampled_from(
    [
        "<html>",
        "<head>",
        "<body>",
        "<title>",
        "</title>",
        "<svg>",
        "</svg>",
        "<math><mi>",
        "<template>",
        "<noscript>",
        "</noscript>",
        "<h1>",
        "<h2>",
        "<br>",
        "<p>",
        "<li>",
        "<meta name=description content=x>",
        "<!--",
        "-->",
        "<",
        ">",
        "&nbsp;",
        "&#0;",
        "\x00",
        " \t\n",
        "a",
    ]
)


@given(st.one_of(st.binary(max_size=300), st.lists(_FRAGMENTS, max_size=30).map("".join)))
def test_the_page_extractor_never_raises(body: str | bytes) -> None:
    # page_row fails on an extractor_error, which is how an extractor's raise is recorded.
    page_row(body)
