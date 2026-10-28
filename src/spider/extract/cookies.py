"""A Page's cookies from its Set-Cookie headers, without their values (030-add-page-data D14)."""

import re
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import get_args

from spider.extract.dates import internet_date
from spider.store.page_records import CookieRow, SameSite

_SAME_SITE: dict[str, SameSite] = {value: value for value in get_args(SameSite.__value__)}
_MAX_AGE = re.compile(r"-?[0-9]+")
# Labels of letters, digits, "-" and "_", which host names in use carry; an IPv4 address
# matches too.
_HOST_NAME = re.compile(r"[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?)*")


def cookie_row(url_id: int, ordinal: int, header: str) -> CookieRow:
    pair, *parts = header.split(";")
    name, mark, _ = pair.partition("=")
    # By name, in order; a flag has no value.
    attributes: dict[str, list[str | None]] = {}
    for part in parts:
        key, equals, value = part.partition("=")
        attributes.setdefault(key.strip().lower(), []).append(value.strip() if equals else None)
    last = {key: values[-1] for key, values in attributes.items()}
    return CookieRow(
        url_id=url_id,
        ordinal=ordinal,
        # Without "=" the whole pair is the value (RFC 6265bis), which is never stored; a token
        # holds no comma, so a name with one is a folded header's value too.
        name=name.strip() if mark and "," not in name else "",
        domain=_last(attributes.get("domain", []), _domain),
        path=_path(last.get("path")),
        expires=_last(attributes.get("expires", []), _expires),
        max_age=_last(attributes.get("max-age", []), _max_age),
        secure="secure" in attributes,
        http_only="httponly" in attributes,
        partitioned="partitioned" in attributes,
        # An unknown SameSite is not ignored (RFC 6265bis 5.6.7): it gives no enforcement.
        same_site=_SAME_SITE.get((last.get("samesite") or "").lower()),
    )


def _last[T](values: Sequence[str | None], read: Callable[[str], T | None]) -> T | None:
    # RFC 6265 5.2 ignores a Domain, Expires or Max-Age whose value does not read, so a
    # repeated one keeps its last valid value.
    for value in reversed(values):
        if value is not None and (read_value := read(value)) is not None:
            return read_value
    return None


def _domain(value: str) -> str | None:
    # RFC 6265 ignores an empty Domain, also one that is only the leading dot. Any other value
    # that is no host name or IP address matches no host (RFC 6265 5.1.3), such as the rest of
    # a header that a proxy folded, which holds the next cookie's value.
    domain = value.lower().removeprefix(".")
    return domain if _HOST_NAME.fullmatch(domain) else None


def _path(value: str | None) -> str | None:
    # RFC 6265 5.2.4 reads a Path that does not start with "/" as the default path. A comma
    # comes from a header that a proxy folded, and what follows it is the next cookie's value.
    if value is None or not value.startswith("/") or "," in value:
        return None
    return value


def _expires(value: str) -> datetime | None:
    return internet_date(value, cookie=True) if value else None


def _max_age(value: str) -> int | None:
    if _MAX_AGE.fullmatch(value) is None:
        return None
    # RFC 6265 reads a Max-Age of any size; SQLite's INTEGER holds 64 bits.
    return min(max(int(value), -(2**63)), 2**63 - 1)
