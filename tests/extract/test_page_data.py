"""The columns the Page extractor derives from the HTML (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_row


def test_charset_declared_in_a_meta_element() -> None:
    body = '<meta charset="windows-1251"><title>Привет</title>'.encode("cp1251")

    assert page_row(body, content_type="text/html").title_1 == "Привет"
