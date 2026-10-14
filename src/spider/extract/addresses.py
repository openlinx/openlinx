"""The display form of a URL (030-add-page-data, Address columns)."""

import re
from contextlib import suppress

from spider.crawl.urls import NormalizedUrl

_ESCAPES = re.compile(r"(?:%[0-9A-Fa-f]{2})+")
# Where surrogateescape puts the bytes that are no UTF-8.
_LOW_SURROGATES = range(0xDC80, 0xDD00)


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
        import idna  # off the startup path

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
        # ASCII and bytes that are no UTF-8 stay escaped, as they were requested.
        if ord(character) < 0x80 or ord(character) in _LOW_SURROGATES:
            parts.append(escapes[position])
            position += 1
        else:
            parts.append(character)
            position += len(character.encode())
    return "".join(parts)
