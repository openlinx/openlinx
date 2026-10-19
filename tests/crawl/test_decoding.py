"""HTML decoding (020-add-crawl-core, crawling; design D5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.pages.decoding import decode_html

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
        (
            b"<!-- <meta charset=koi8-r> -->\xc3\xa9",
            None,
            ("<!-- <meta charset=koi8-r> -->é", "utf-8"),
        ),
        (
            b'<meta name="description" content="charset=koi8-r">\xc3\xa9',
            None,
            ('<meta name="description" content="charset=koi8-r">é', "utf-8"),
        ),
        (b"<metadata charset=koi8-r>\xc3\xa9", None, ("<metadata charset=koi8-r>é", "utf-8")),
        (
            b"<meta charset=nonsense><meta charset=koi8-r>\xd6",
            None,
            ("<meta charset=nonsense><meta charset=koi8-r>ж", "koi8-r"),
        ),
        (b"\x82\xa0", "text/html; charset=x-sjis", ("\N{HIRAGANA LETTER A}", "shift_jis")),
        (b"\xe9", "text/html; charset=x-cp1251", ("й", "windows-1251")),
        (
            b"\xe0",
            "text/html; charset=iso-8859-8-i",
            ("\N{HEBREW LETTER ALEF}", "iso-8859-8-i"),
        ),
        (b"caf\xe9", "text/html; charset=u8", ("café", "windows-1252")),
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


@pytest.mark.parametrize(
    ("label", "encoding"),
    [
        ("unicode-1-1-utf-8", "utf-8"),
        ("866", "ibm866"),
        ("latin2", "iso-8859-2"),
        ("l3", "iso-8859-3"),
        ("iso-ir-110", "iso-8859-4"),
        ("cyrillic", "iso-8859-5"),
        ("asmo-708", "iso-8859-6"),
        ("sun_eu_greek", "iso-8859-7"),
        ("visual", "iso-8859-8"),
        ("logical", "iso-8859-8-i"),
        ("latin6", "iso-8859-10"),
        ("iso885913", "iso-8859-13"),
        ("iso8859-14", "iso-8859-14"),
        ("l9", "iso-8859-15"),
        ("iso-8859-16", "iso-8859-16"),
        ("koi", "koi8-r"),
        ("koi8-ru", "koi8-u"),
        ("mac", "macintosh"),
        ("dos-874", "windows-874"),
        ("x-cp1250", "windows-1250"),
        ("cp1251", "windows-1251"),
        ("ansi_x3.4-1968", "windows-1252"),
        ("x-cp1253", "windows-1253"),
        ("l5", "windows-1254"),
        ("x-cp1255", "windows-1255"),
        ("cp1256", "windows-1256"),
        ("x-cp1257", "windows-1257"),
        ("cp1258", "windows-1258"),
        ("x-mac-ukrainian", "x-mac-cyrillic"),
        ("chinese", "gbk"),
        ("gb18030", "gb18030"),
        ("cn-big5", "big5"),
        ("cseucpkdfmtjapanese", "euc-jp"),
        ("csiso2022jp", "iso-2022-jp"),
        ("windows-31j", "shift_jis"),
        ("ks_c_5601-1989", "euc-kr"),
        ("unicodefffe", "utf-16be"),
        ("ucs-2", "utf-16le"),
        ("x-user-defined", "utf-8"),
        ("iso-2022-kr", "utf-8"),
    ],
)
def test_each_encoding_of_the_standard_is_named_by_its_labels(label: str, encoding: str) -> None:
    assert decode_html(b"a", f"text/html; charset={label.upper()}").encoding == encoding
