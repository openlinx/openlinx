"""The display form of a Page's address, and its path and query (030-add-page-data, the Address
columns)."""

import re
import unicodedata
from contextlib import suppress

import idna

from spider.crawl.urls import NormalizedUrl

_ESCAPES = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
# Where surrogateescape puts the bytes that are no UTF-8.
_LOW_SURROGATES = range(0xDC80, 0xDD00)
# Controls, format characters such as bidi overrides, and spaces and separators: shown raw,
# they hide or spoof what the address says, so they stay encoded.
_KEPT_ENCODED = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})


def display_address(url: NormalizedUrl) -> str:
    """The host in Unicode, and every escaped UTF-8 sequence of a non-ASCII character decoded."""
    scheme, _, rest = url.partition("://")
    # A normalised URL always has a path, so its authority ends at the first slash.
    authority, _, path = rest.partition("/")
    return f"{scheme}://{_unicode_host(authority)}/{_ESCAPES.sub(_decoded, path)}"


def _unicode_host(host: str) -> str:
    if "xn--" not in host:
        return host
    name, colon, port = host.partition(":")
    return ".".join(map(_unicode_label, name.split("."))) + colon + port


def _unicode_label(label: str) -> str:
    if label.startswith("xn--"):
        # A label that does not decode stays as it was requested.
        with suppress(idna.IDNAError):
            return idna.decode(label)
    return label


def _decoded(match: re.Match[str]) -> str:
    run = match[0]
    escapes = [run[start : start + 3] for start in range(0, len(run), 3)]
    text = bytes(int(escape[1:], 16) for escape in escapes).decode("utf-8", "surrogateescape")
    parts = []
    position = 0
    for character in text:
        size = 1 if ord(character) in _LOW_SURROGATES else len(character.encode())
        # ASCII and bytes that are no UTF-8 stay escaped, as they were requested.
        if size == 1 or unicodedata.category(character) in _KEPT_ENCODED:
            parts.append("".join(escapes[position : position + size]))
        else:
            parts.append(character)
        position += size
    return "".join(parts)


def path_and_query(address: str) -> tuple[str, str | None]:
    """The query is None without a "?", and "" when nothing follows it."""
    after_host = address.partition("://")[2].partition("/")[2]
    path, mark, query = ("/" + after_host).partition("?")
    return path, query if mark else None
