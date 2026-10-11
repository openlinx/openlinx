"""URL normalisation: NormalizedUrl, made only here (020-add-crawl-core D13)."""

import re
import string
from dataclasses import dataclass
from typing import NewType
from urllib.parse import SplitResult, urlsplit, urlunsplit

NormalizedUrl = NewType("NormalizedUrl", str)

_DEFAULT_PORTS = {"http": 80, "https": 443}
_PERCENT_ENCODED = re.compile("%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]|%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True, slots=True)
class InvalidUrl:
    reason: str


def normalize_url(text: str) -> NormalizedUrl | InvalidUrl:
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return InvalidUrl("malformed")
    if parts.scheme not in _DEFAULT_PORTS:
        return InvalidUrl("unsupported_scheme")
    if not parts.hostname:
        return InvalidUrl("missing_host")
    return NormalizedUrl(urlunsplit(_normalized_parts(parts, port)))


def _normalized_parts(parts: SplitResult, port: int | None) -> SplitResult:
    netloc = parts.hostname or ""
    if port is not None and port != _DEFAULT_PORTS[parts.scheme]:
        netloc = f"{netloc}:{port}"
    path = _without_dot_segments(_percent_normalized(parts.path))
    query = _percent_normalized(parts.query)
    return parts._replace(netloc=netloc, path=path, query=query, fragment="")


def _percent_normalized(text: str) -> str:
    encoded = _NOT_ALLOWED.sub(_escape, text)
    return _PERCENT_ENCODED.sub(_normalized_escape, encoded)


def _escape(match: re.Match[str]) -> str:
    return "".join(f"%{byte:02X}" for byte in match[0].encode())


def _normalized_escape(match: re.Match[str]) -> str:
    character = chr(int(match[1], 16))
    return character if character in _UNRESERVED else f"%{match[1].upper()}"


def _without_dot_segments(path: str) -> str:
    segments: list[str] = []
    for segment in path.split("/")[1:]:
        if segment == "..":
            if segments:
                segments.pop()
        elif segment != ".":
            segments.append(segment)
    # A path that ends in a dot segment names a folder, so it ends in a slash (RFC 3986 5.2.4).
    if path.endswith(("/.", "/..")):
        segments.append("")
    return "/" + "/".join(segments)
