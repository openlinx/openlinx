"""URL normalisation: NormalizedUrl, made only here (020-add-crawl-core D13)."""

import re
import string
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Address, IPv6Address
from typing import Literal, NewType
from urllib.parse import SplitResult, urlsplit, urlunsplit

NormalizedUrl = NewType("NormalizedUrl", str)
# URLs that normalisation would leave unchanged; most resolved Links are already in this form.
NORMAL_FORM = re.compile(
    r"https?://[a-z0-9\-._~]+"
    r"(?:/(?!\.\.?(?:/|\?|$))[A-Za-z0-9\-._~:@!$&'()*+,;=]*)+"
    r"(?:\?[A-Za-z0-9\-._~:@!$&'()*+,;=/?]+)?"
)
type InvalidUrlReason = Literal[
    "malformed", "unsupported_scheme", "userinfo", "missing_host", "invalid_host"
]

_DEFAULT_PORTS = {"http": 80, "https": 443}
# A stray % is matched with no group, so it is encoded before any escape is decoded.
_PERCENT = re.compile("%([0-9A-Fa-f]{2})?")
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
# "[" and "]" belong to an IPv6 host only, so the path and the query encode them.
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9\-._~:/?#@!$&'()*+,;=%]+")
_BYTE_ESCAPES = tuple(f"%{byte:02X}" for byte in range(256))
_HOST = re.compile(r"[a-z0-9\-._~]+")
# "localhost:8080" is a host and a port; "mailto:a@b.test" names the scheme mailto.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:(?![0-9]+(?:[/?#]|$))")
_GLOB_WILDCARDS = {"*": ".*", "?": "."}
_SURROGATE = re.compile(r"[\ud800-\udfff]")
# UTS46 deletes these silently, so "e<ZWSP>vil.test" would become "evil.test"; aiohttp's URL
# library (yarl) refuses the same set.
_IGNORABLE = re.compile(
    "[\u00ad\u034f\u061c\u115f-\u1160\u17b4-\u17b5\u1806\u180b-\u180f\u200b-\u200f\u202a-\u202e"
    "\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8\U0001bca0-\U0001bca3"
    "\U0001d173-\U0001d17a\U000e0000-\U000e0fff]"
)


@dataclass(frozen=True, slots=True)
class InvalidUrl:
    reason: InvalidUrlReason


def strip_params_pattern(values: Sequence[str]) -> re.Pattern[str] | None:
    """One pattern for --strip-params, from flag values that each hold comma-separated globs."""
    globs = [glob for value in values for glob in value.split(",") if glob]
    if not globs:
        return None
    return re.compile("|".join(_glob_regex(glob) for glob in globs))


def _glob_regex(glob: str) -> str:
    return "".join(_GLOB_WILDCARDS.get(character, re.escape(character)) for character in glob)


def normalize_url(
    text: str, strip_params: re.Pattern[str] | None = None
) -> NormalizedUrl | InvalidUrl:
    if NORMAL_FORM.fullmatch(text) and (strip_params is None or "?" not in text):
        return NormalizedUrl(text)
    # A lone surrogate, as surrogateescape decoding leaves, has no UTF-8 form to percent-encode.
    if _SURROGATE.search(text):
        return InvalidUrl("malformed")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return InvalidUrl("malformed")
    if parts.scheme not in _DEFAULT_PORTS:
        return InvalidUrl("unsupported_scheme")
    if "@" in parts.netloc:
        return InvalidUrl("userinfo")
    if not parts.hostname:
        return InvalidUrl("missing_host")
    host = _ascii_host(_raw_host(parts.netloc))
    if host is None:
        return InvalidUrl("invalid_host")
    return NormalizedUrl(urlunsplit(_normalized_parts(parts, host, port, strip_params)))


def parse_seed(
    text: str, strip_params: re.Pattern[str] | None = None
) -> NormalizedUrl | InvalidUrl:
    seed = text.strip()
    return normalize_url(seed if _SCHEME.match(seed) else f"https://{seed}", strip_params)


def _raw_host(netloc: str) -> str:
    if netloc.startswith("["):
        return netloc.partition("]")[0] + "]"
    return netloc.partition(":")[0]


# A site's hosts repeat, and IDNA takes about 40 us a host: every Link of a .рф site would pay it.
@lru_cache(maxsize=1024)
def _ascii_host(host: str) -> str | None:
    """Encoded as aiohttp encodes it, so that the host recorded is the host requested."""
    if host.startswith("["):
        return _ipv6_host(host[1:-1])
    if host[-1].isdigit():
        try:
            return str(IPv4Address(host))
        except ValueError:
            pass
    encoded = host.lower() if host.isascii() else _idna_encoded(host)
    return encoded if encoded is not None and _HOST.fullmatch(encoded) else None


def _ipv6_host(address: str) -> str | None:
    # A bracketed host that is not IPv6 (IPvFuture, "[v1.x]") must not become the name "v1.x".
    try:
        return f"[{IPv6Address(address).compressed}]"
    except ValueError:
        return None


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


def _normalized_parts(
    parts: SplitResult, host: str, port: int | None, strip_params: re.Pattern[str] | None
) -> SplitResult:
    netloc = host
    if port is not None and port != _DEFAULT_PORTS[parts.scheme]:
        netloc = f"{netloc}:{port}"
    path = _without_dot_segments(_percent_normalized(parts.path))
    query = _percent_normalized(parts.query)
    if strip_params is not None:
        query = _without_params(query, strip_params)
    return parts._replace(netloc=netloc, path=path, query=query, fragment="")


def _without_params(query: str, strip_params: re.Pattern[str]) -> str:
    params = query.split("&")
    return "&".join(param for param in params if not strip_params.fullmatch(_name(param)))


def _name(param: str) -> str:
    return param.partition("=")[0]


def _percent_normalized(text: str) -> str:
    if "%" in text:
        text = _PERCENT.sub(_normalized_escape, text)
    return _NOT_ALLOWED.sub(_escape, text)


def _escape(match: re.Match[str]) -> str:
    return "".join(map(_BYTE_ESCAPES.__getitem__, match[0].encode()))


def _normalized_escape(match: re.Match[str]) -> str:
    if match[1] is None:
        return "%25"
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


def without_www(url: NormalizedUrl) -> NormalizedUrl:
    """The URL on its host without a leading www. label, which keeps the normal form."""
    scheme, rest = url.split("://", 1)
    return NormalizedUrl(f"{scheme}://{rest.removeprefix('www.')}")


def url_host(url: NormalizedUrl) -> str:
    authority = url.split("/", 3)[2]
    if authority.startswith("["):
        return authority.partition("]")[0] + "]"
    return authority.partition(":")[0]


def url_origin(url: NormalizedUrl) -> str:
    """The scheme, host and port: a normalised URL has left out a default port already."""
    return "/".join(url.split("/", 3)[:3])


def url_path(url: NormalizedUrl) -> str:
    return "/" + url.split("/", 3)[3].partition("?")[0]
