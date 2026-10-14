"""The columns the Page extractor derives from the HTML (030-add-page-data, page-data; seam 4)."""

from hypothesis import given
from hypothesis import strategies as st

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


# Fragments that build the documents a parser repairs: unclosed, nested in foreign content,
# commented out, NUL and stray markup.
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
