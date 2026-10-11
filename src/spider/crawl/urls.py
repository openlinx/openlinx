"""URL normalisation: NormalizedUrl, made only here (020-add-crawl-core D13)."""

import re
import string
from dataclasses import dataclass
from ipaddress import ip_address
from typing import NewType
from urllib.parse import SplitResult, urlsplit, urlunsplit

NormalizedUrl = NewType("NormalizedUrl", str)

_DEFAULT_PORTS = {"http": 80, "https": 443}
_PERCENT_ENCODED = re.compile("%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]|%(?![0-9A-Fa-f]{2})")
_HOST = re.compile(r"[a-z0-9\-._~]+")
# UTS46 deletes these silently, so "e<ZWSP>vil.test" would become "evil.test"; aiohttp's URL
# library (yarl) refuses the same set.
_IGNORABLE = re.compile(
    "[\u00ad\u034f\u061c\u115f-\u1160\u17b4-\u17b5\u1806\u180b-\u180f\u200b-\u200f\u202a-\u202e"
    "\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8\U0001bca0-\U0001bca3"
    "\U0001d173-\U0001d17a\U000e0000-\U000e0fff]"
)


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
    host = _ascii_host(_raw_host(parts.netloc))
    if host is None:
        return InvalidUrl("invalid_host")
    return NormalizedUrl(urlunsplit(_normalized_parts(parts, host, port)))


def _raw_host(netloc: str) -> str:
    hostinfo = netloc.rpartition("@")[2]
    before, bracket, bracketed = hostinfo.partition("[")
    if bracket:
        return bracketed.partition("]")[0]
    return before.partition(":")[0]


def _ascii_host(host: str) -> str | None:
    """The host as aiohttp requests it, so the host recorded is the host requested."""
    if host[-1].isdigit() or ":" in host:
        try:
            address = ip_address(host)
        except ValueError:
            pass
        else:
            return f"[{address.compressed}]" if address.version == 6 else address.compressed
    encoded = host.lower() if host.isascii() else _idna_encoded(host)
    return encoded if encoded is not None and _HOST.fullmatch(encoded) else None


def _idna_encoded(host: str) -> str | None:
    if _IGNORABLE.search(host):
        return None
    import idna  # off the startup path

    try:
        return idna.encode(host, uts46=True).decode("ascii").lower()
    except UnicodeError:
        pass
    # aiohttp's URL library falls back to the built-in IDNA 2003 codec too.
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None


def _normalized_parts(parts: SplitResult, host: str, port: int | None) -> SplitResult:
    netloc = host
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
