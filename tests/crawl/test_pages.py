"""Which responses are HTML (020-add-crawl-core D5; seam 4)."""

import pytest

from openlinx.crawl.pages.preparation import is_html_type


@pytest.mark.parametrize(
    ("content_type", "html"),
    [
        ("text/html", True),
        ("text/html; charset=utf-8", True),
        ("Text/HTML", True),
        (" text/html ;charset=utf-8", True),
        ("application/xhtml+xml", True),
        ("application/xhtml+xml; charset=utf-8", True),
        ("text/plain", False),
        ("application/xml", False),
        ("text/htmlx", False),
        ("", False),
        (None, False),
    ],
)
def test_a_content_type_is_html_by_its_media_type(content_type: str | None, html: bool) -> None:
    assert is_html_type(content_type) is html
