"""HTML decoding, shared with 030's text (020-add-crawl-core D5)."""

import codecs
import re
from dataclasses import dataclass

# The Encoding Standard's names, each with the Python codec that decodes it.
_CODECS = {
    "utf-8": "utf-8",
    "utf-16le": "utf-16-le",
    "utf-16be": "utf-16-be",
    "ibm866": "cp866",
    "iso-8859-2": "iso8859-2",
    "iso-8859-3": "iso8859-3",
    "iso-8859-4": "iso8859-4",
    "iso-8859-5": "iso8859-5",
    "iso-8859-6": "iso8859-6",
    "iso-8859-7": "iso8859-7",
    "iso-8859-8": "iso8859-8",
    "iso-8859-10": "iso8859-10",
    "iso-8859-13": "iso8859-13",
    "iso-8859-14": "iso8859-14",
    "iso-8859-15": "iso8859-15",
    "iso-8859-16": "iso8859-16",
    "koi8-r": "koi8-r",
    "koi8-u": "koi8-u",
    "macintosh": "mac-roman",
    "x-mac-cyrillic": "mac-cyrillic",
    "windows-874": "cp874",
    "windows-1250": "cp1250",
    "windows-1251": "cp1251",
    "windows-1252": "cp1252",
    "windows-1253": "cp1253",
    "windows-1254": "cp1254",
    "windows-1255": "cp1255",
    "windows-1256": "cp1256",
    "windows-1257": "cp1257",
    "windows-1258": "cp1258",
    "gbk": "gbk",
    "gb18030": "gb18030",
    "big5": "big5hkscs",
    "euc-jp": "euc-jp",
    "iso-2022-jp": "iso2022-jp",
    "shift_jis": "cp932",
    "euc-kr": "cp949",
}
# Python codecs whose labels the Standard maps to another encoding, mostly a Windows superset.
_SUPERSETS = {
    "ascii": "windows-1252",
    "iso8859-1": "windows-1252",
    "iso8859-9": "windows-1254",
    "iso8859-11": "windows-874",
    "tis-620": "windows-874",
    "gb2312": "gbk",
    "big5": "big5",
    "shift_jis": "shift_jis",
    "euc_kr": "euc-kr",
    "utf-16": "utf-16le",
}
_BY_CODEC = {codecs.lookup(codec).name: name for name, codec in _CODECS.items()} | _SUPERSETS
_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_BE, "utf-16be"),
    (codecs.BOM_UTF16_LE, "utf-16le"),
)
_CONTENT_TYPE_CHARSET = re.compile(r';\s*charset\s*=\s*(?:"([^"]*)"|([^;\s]*))', re.IGNORECASE)
_META_CHARSET = re.compile(r"""<meta[^>]*?charset\s*=\s*["']?\s*([^"'\s;/>]+)""", re.IGNORECASE)
_META_PRESCAN_BYTES = 1024


@dataclass(frozen=True, slots=True)
class DecodedHtml:
    text: str
    encoding: str


def decode_html(body: bytes, content_type: str | None) -> DecodedHtml:
    for mark, marked in _BYTE_ORDER_MARKS:
        if body.startswith(mark):
            return _decoded(body[len(mark) :], marked)
    match = _CONTENT_TYPE_CHARSET.search(content_type or "")
    name = _encoding(match[1] or match[2]) if match else None
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


def _encoding(label: str) -> str | None:
    try:
        codec = codecs.lookup(label.strip())
    except (LookupError, ValueError):  # ValueError: a NUL or a lone surrogate in the label
        return None
    return _BY_CODEC.get(codec.name)


def _meta_encoding(head: bytes) -> str | None:
    match = _META_CHARSET.search(head.decode("latin-1"))
    name = _encoding(match[1]) if match else None
    # A declaration read from ASCII-compatible bytes cannot be UTF-16.
    return "utf-8" if name in ("utf-16le", "utf-16be") else name
