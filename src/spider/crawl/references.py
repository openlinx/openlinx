"""Reference resolution as browsers do it, and the Link record (020-add-crawl-core D5, D19)."""

import re
from urllib.parse import urljoin

import msgspec

from spider.crawl.urls import NormalizedUrl, normalize_url
from spider.store.records import DeclaredIn, LinkType

# The URL Standard strips these around a reference and removes tabs and newlines inside it;
# urlsplit strips only the leading ones.
C0_OR_SPACE = "".join(map(chr, range(0x21)))
_TAB_OR_NEWLINE = str.maketrans("", "", "\t\n\r")
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
_HTTP_SCHEMES = frozenset({"http", "https"})
# In http and https URLs browsers read a backslash as a slash, before the query.
_SLASHES = "/\\"
_QUERY_OR_FRAGMENT = re.compile(r"[?#]")


class DiscoveredLink(msgspec.Struct, frozen=True, kw_only=True):
    type: LinkType
    target: NormalizedUrl
    raw: str
    element: str | None
    attribute: str | None
    rel: tuple[str, ...]
    nofollow: bool
    # Whether the Crawl requests the target through this Link (spider.crawl.following).
    requests_target: bool
    declared_in: DeclaredIn
    ordinal: int
    is_internal: bool


def resolve_reference(
    base: str, raw: str, codec: str | None, strip_params: re.Pattern[str] | None
) -> NormalizedUrl | None:
    """The normalised URL a browser makes of a reference against `base`, or None."""
    joined = _joined(base, _cleaned(raw), codec)
    if joined is None:
        return None
    target = normalize_url(joined, strip_params)
    return target if isinstance(target, str) else None


def resolve_base(url: NormalizedUrl, href: str, codec: str | None) -> str:
    href = _cleaned(href)
    scheme = _SCHEME.match(href)
    # Unnormalised, as browsers resolve against it: a javascript: base resolves nothing.
    if scheme is not None and scheme[1].lower() not in _HTTP_SCHEMES:
        return href
    return _joined(url, href, codec) or url


def _cleaned(raw: str) -> str:
    return raw.strip(C0_OR_SPACE).translate(_TAB_OR_NEWLINE)


def _joined(base: str, reference: str, codec: str | None) -> str | None:
    """The http or https URL a browser makes of the reference, or None (URL Standard)."""
    base_scheme = base.partition(":")[0]
    match = _SCHEME.match(reference)
    if match is not None:
        scheme = match[1].lower()
        if scheme not in _HTTP_SCHEMES:
            return None
        # The base's own scheme makes a relative reference; the other one names a host.
        if scheme != base_scheme:
            return _with_host(scheme, reference[match.end() :], codec)
        reference = reference[match.end() :]
    if base_scheme not in _HTTP_SCHEMES:
        return None
    if reference[0:1] in ("/", "\\") and reference[1:2] in ("/", "\\"):
        return _with_host(base_scheme, reference, codec)
    try:
        joined = urljoin(base, _forward_slashes(reference))
    except ValueError:
        return None
    return _query_encoded(joined, codec)


def _with_host(scheme: str, rest: str, codec: str | None) -> str | None:
    rest = _forward_slashes(rest.lstrip(_SLASHES))
    if rest[:1] in ("", "/", "?", "#"):
        return None
    return _query_encoded(f"{scheme}://{rest}", codec)


def _forward_slashes(reference: str) -> str:
    if "\\" not in reference:
        return reference
    end = _QUERY_OR_FRAGMENT.search(reference)
    split = end.start() if end is not None else len(reference)
    return reference[:split].replace("\\", "/") + reference[split:]


def _query_encoded(url: str, codec: str | None) -> str:
    if codec is None or url.isascii():
        return url
    url, hash_mark, fragment = url.partition("#")
    head, question_mark, query = url.partition("?")
    if query.isascii():
        return f"{url}{hash_mark}{fragment}"
    data = query.encode(codec, "xmlcharrefreplace")
    # The "#" of a character reference would otherwise end the query.
    encoded = "".join(chr(b) if b < 0x80 else f"%{b:02X}" for b in data).replace("#", "%23")
    return f"{head}{question_mark}{encoded}{hash_mark}{fragment}"
