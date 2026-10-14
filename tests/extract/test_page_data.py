"""The columns the Page extractor derives from the HTML (030-add-page-data, page-data; seam 4)."""

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
