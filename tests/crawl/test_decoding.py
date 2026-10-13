"""HTML decoding (020-add-crawl-core, crawling; design D5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.decoding import decode_html

_CP1251 = "text/html; charset=windows-1251"


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        (b"\xef\xbb\xbfcaf\xc3\xa9", _CP1251, ("café", "utf-8")),
        (b"\xff\xfeh\x00\xe9\x00", _CP1251, ("hé", "utf-16le")),
        (b"\xfe\xff\x00h\x00\xe9", None, ("hé", "utf-16be")),
        (b"<meta charset=utf-8>\xe9", _CP1251, ("<meta charset=utf-8>й", "windows-1251")),
        (b"\xd6", 'text/html; Charset="KOI8-R"', ("ж", "koi8-r")),
        (b"\x80", "text/html;charset=ISO-8859-1", ("€", "windows-1252")),
        (b"\xd0", "text/html; charset=latin5", ("Ğ", "windows-1254")),
        (b"\xc3\xa9", "text/html; charset=base64", ("é", "utf-8")),
        (
            b"<META CHARSET='windows-1251'>\xe9",
            "text/html; charset=nonsense",
            ("<META CHARSET='windows-1251'>й", "windows-1251"),
        ),
        (
            b'<meta http-equiv="Content-Type" content="text/html; charset=koi8-r">\xd6',
            "text/html",
            ('<meta http-equiv="Content-Type" content="text/html; charset=koi8-r">ж', "koi8-r"),
        ),
        (b"<meta charset=utf-16>\xc3\xa9", None, ("<meta charset=utf-16>é", "utf-8")),
        (
            b" " * 1024 + b"<meta charset=koi8-r>\xc3\xa9",
            None,
            (" " * 1024 + "<meta charset=koi8-r>é", "utf-8"),
        ),
        (b"caf\xe9", None, ("café", "windows-1252")),
        (b"a\xffb", "text/html; charset=utf-8", ("a\N{REPLACEMENT CHARACTER}b", "utf-8")),
    ],
)
def test_html_is_decoded_by_the_first_source_that_applies(
    body: bytes, content_type: str | None, expected: tuple[str, str]
) -> None:
    decoded = decode_html(body, content_type)

    assert (decoded.text, decoded.encoding) == expected


_CONTENT_TYPES = st.none() | st.text() | st.text().map("text/html; charset={}".format)


@given(st.binary(), _CONTENT_TYPES)
def test_decoding_any_bytes_gives_text(body: bytes, content_type: str | None) -> None:
    decoded = decode_html(body, content_type)

    assert isinstance(decoded.text, str)
