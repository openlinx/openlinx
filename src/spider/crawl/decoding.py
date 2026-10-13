"""HTML decoding, shared with 030's text (020-add-crawl-core D5)."""

import codecs
import re
from collections.abc import Mapping
from dataclasses import dataclass

# The labels of the Encoding Standard (encoding.spec.whatwg.org/encodings.json), by the
# encoding's name in lower case, as TextDecoder reports it. Python's codecs know other labels
# (u8, cp65001) and miss some of these (x-sjis, x-cp1251). x-user-defined and the replacement
# encoding have no Python codec, so their labels are skipped like unknown ones.
_LABELS_BY_ENCODING: Mapping[str, str] = {
    "utf-8": "unicode-1-1-utf-8 unicode11utf8 unicode20utf8 utf-8 utf8 x-unicode20utf8",
    "ibm866": "866 cp866 csibm866 ibm866",
    "iso-8859-2": (
        "csisolatin2 iso-8859-2 iso-ir-101 iso8859-2 iso88592 iso_8859-2 iso_8859-2:1987 l2 latin2"
    ),
    "iso-8859-3": (
        "csisolatin3 iso-8859-3 iso-ir-109 iso8859-3 iso88593 iso_8859-3 iso_8859-3:1988 l3 latin3"
    ),
    "iso-8859-4": (
        "csisolatin4 iso-8859-4 iso-ir-110 iso8859-4 iso88594 iso_8859-4 iso_8859-4:1988 l4 latin4"
    ),
    "iso-8859-5": (
        "csisolatincyrillic cyrillic iso-8859-5 iso-ir-144 iso8859-5 iso88595 iso_8859-5 "
        "iso_8859-5:1988"
    ),
    "iso-8859-6": (
        "arabic asmo-708 csiso88596e csiso88596i csisolatinarabic ecma-114 iso-8859-6 "
        "iso-8859-6-e iso-8859-6-i iso-ir-127 iso8859-6 iso88596 iso_8859-6 iso_8859-6:1987"
    ),
    "iso-8859-7": (
        "csisolatingreek ecma-118 elot_928 greek greek8 iso-8859-7 iso-ir-126 iso8859-7 iso88597 "
        "iso_8859-7 iso_8859-7:1987 sun_eu_greek"
    ),
    "iso-8859-8": (
        "csiso88598e csisolatinhebrew hebrew iso-8859-8 iso-8859-8-e iso-ir-138 iso8859-8 "
        "iso88598 iso_8859-8 iso_8859-8:1988 visual"
    ),
    "iso-8859-8-i": "csiso88598i iso-8859-8-i logical",
    "iso-8859-10": "csisolatin6 iso-8859-10 iso-ir-157 iso8859-10 iso885910 l6 latin6",
    "iso-8859-13": "iso-8859-13 iso8859-13 iso885913",
    "iso-8859-14": "iso-8859-14 iso8859-14 iso885914",
    "iso-8859-15": "csisolatin9 iso-8859-15 iso8859-15 iso885915 iso_8859-15 l9",
    "iso-8859-16": "iso-8859-16",
    "koi8-r": "cskoi8r koi koi8 koi8-r koi8_r",
    "koi8-u": "koi8-ru koi8-u",
    "macintosh": "csmacintosh mac macintosh x-mac-roman",
    "windows-874": "dos-874 iso-8859-11 iso8859-11 iso885911 tis-620 windows-874",
    "windows-1250": "cp1250 windows-1250 x-cp1250",
    "windows-1251": "cp1251 windows-1251 x-cp1251",
    "windows-1252": (
        "ansi_x3.4-1968 ascii cp1252 cp819 csisolatin1 ibm819 iso-8859-1 iso-ir-100 iso8859-1 "
        "iso88591 iso_8859-1 iso_8859-1:1987 l1 latin1 us-ascii windows-1252 x-cp1252"
    ),
    "windows-1253": "cp1253 windows-1253 x-cp1253",
    "windows-1254": (
        "cp1254 csisolatin5 iso-8859-9 iso-ir-148 iso8859-9 iso88599 iso_8859-9 iso_8859-9:1989 "
        "l5 latin5 windows-1254 x-cp1254"
    ),
    "windows-1255": "cp1255 windows-1255 x-cp1255",
    "windows-1256": "cp1256 windows-1256 x-cp1256",
    "windows-1257": "cp1257 windows-1257 x-cp1257",
    "windows-1258": "cp1258 windows-1258 x-cp1258",
    "x-mac-cyrillic": "x-mac-cyrillic x-mac-ukrainian",
    "gbk": "chinese csgb2312 csiso58gb231280 gb2312 gb_2312 gb_2312-80 gbk iso-ir-58 x-gbk",
    "gb18030": "gb18030",
    "big5": "big5 big5-hkscs cn-big5 csbig5 x-x-big5",
    "euc-jp": "cseucpkdfmtjapanese euc-jp x-euc-jp",
    "iso-2022-jp": "csiso2022jp iso-2022-jp",
    "shift_jis": "csshiftjis ms932 ms_kanji shift-jis shift_jis sjis windows-31j x-sjis",
    "euc-kr": (
        "cseuckr csksc56011987 euc-kr iso-ir-149 korean ks_c_5601-1987 ks_c_5601-1989 ksc5601 "
        "ksc_5601 windows-949"
    ),
    "utf-16be": "unicodefffe utf-16be",
    "utf-16le": "csunicode iso-10646-ucs-2 ucs-2 unicode unicodefeff utf-16 utf-16le",
}
_LABELS = {label: name for name, labels in _LABELS_BY_ENCODING.items() for label in labels.split()}
# The Standard decodes GBK with the gb18030 decoder, Big5 with HKSCS, and Shift_JIS and EUC-KR
# with Windows' supersets of them.
_CODECS = {name: name for name in _LABELS_BY_ENCODING} | {
    "ibm866": "cp866",
    "iso-8859-8-i": "iso8859-8",
    "macintosh": "mac-roman",
    "x-mac-cyrillic": "mac-cyrillic",
    "windows-874": "cp874",
    "gbk": "gb18030",
    "big5": "big5hkscs",
    "shift_jis": "cp932",
    "euc-kr": "cp949",
    "utf-16be": "utf-16-be",
    "utf-16le": "utf-16-le",
}
_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_BE, "utf-16be"),
    (codecs.BOM_UTF16_LE, "utf-16le"),
)
_ASCII_WHITESPACE = "\t\n\x0c\r "
_CONTENT_TYPE_CHARSET = re.compile(r';\s*charset\s*=\s*(?:"([^"]*)"|([^;\s]*))', re.IGNORECASE)
_META_PRESCAN_BYTES = 1024
_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
_META = re.compile(r"<meta[\t\n\x0c\r /]([^>]*)", re.IGNORECASE)
_SPACES = r"[\t\n\x0c\r ]*"
_ATTRIBUTE = re.compile(
    rf"""([^\t\n\x0c\r />=]+){_SPACES}(?:={_SPACES}(?:"([^"]*)"|'([^']*)'|([^\t\n\x0c\r >]*)))?"""
)
_CONTENT_CHARSET = re.compile(
    rf"""charset{_SPACES}={_SPACES}["']?([^"';\t\n\x0c\r ]+)""", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class DecodedHtml:
    text: str
    encoding: str


def decode_html(body: bytes, content_type: str | None) -> DecodedHtml:
    for mark, marked in _BYTE_ORDER_MARKS:
        if body.startswith(mark):
            return _decoded(body[len(mark) :], marked)
    match = _CONTENT_TYPE_CHARSET.search(content_type or "")
    name = _LABELS.get(_label(match[1] or match[2])) if match else None
    if name is None:
        name = _meta_encoding(body[:_META_PRESCAN_BYTES])
    if name is not None:
        return _decoded(body, name)
    try:
        return DecodedHtml(body.decode("utf-8"), "utf-8")
    except UnicodeDecodeError:
        return _decoded(body, "windows-1252")


def _decoded(body: bytes, name: str) -> DecodedHtml:
    return DecodedHtml(body.decode(_CODECS[name], "replace"), name)


def _label(text: str) -> str:
    return text.strip(_ASCII_WHITESPACE).lower()


def _meta_encoding(head: bytes) -> str | None:
    for meta in _META.finditer(_COMMENT.sub("", head.decode("latin-1"))):
        attributes: dict[str, str] = {}
        for attribute in _ATTRIBUTE.finditer(meta[1]):
            value = attribute[2] or attribute[3] or attribute[4] or ""
            attributes.setdefault(attribute[1].lower(), value)
        label = attributes.get("charset")
        if label is None and _label(attributes.get("http-equiv", "")) == "content-type":
            charset = _CONTENT_CHARSET.search(attributes.get("content", ""))
            label = charset[1] if charset else None
        name = _LABELS.get(_label(label)) if label is not None else None
        if name is not None:
            # A declaration read from ASCII-compatible bytes cannot be UTF-16.
            return "utf-8" if name in ("utf-16le", "utf-16be") else name
    return None
