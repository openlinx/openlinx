"""A Page's cookies from its Set-Cookie headers, without their values (030-add-page-data D14)."""

import re
from datetime import datetime

from spider.extract.dates import internet_date
from spider.store.page_records import CookieRow, SameSite

_SAME_SITE: dict[str, SameSite] = {"strict": "strict", "lax": "lax", "none": "none"}
# ASCII digits only (RFC 6265 5.2.2): \d would take any script's digits.
_MAX_AGE = re.compile(r"-?[0-9]+")
_INTEGER_RANGE = range(-(2**63), 2**63)


def cookie_row(url_id: int, ordinal: int, header: str) -> CookieRow:
    pair, *parts = header.split(";")
    name, mark, _ = pair.partition("=")
    # By name, the last of a repeated attribute winning (RFC 6265 5.3); a flag has no value.
    attributes: dict[str, str | None] = {}
    for part in parts:
        key, equals, value = part.partition("=")
        attributes[key.strip().lower()] = value.strip() if equals else None
    return CookieRow(
        url_id=url_id,
        ordinal=ordinal,
        # Without "=" the whole pair is the value (RFC 6265bis), which is never stored.
        name=name.strip() if mark else "",
        domain=_domain(attributes.get("domain")),
        path=attributes.get("path"),
        expires=_expires(attributes.get("expires")),
        max_age=_max_age(attributes.get("max-age")),
        secure="secure" in attributes,
        http_only="httponly" in attributes,
        partitioned="partitioned" in attributes,
        same_site=_SAME_SITE.get((attributes.get("samesite") or "").lower()),
    )


def _domain(value: str | None) -> str | None:
    if value is None:
        return None
    # RFC 6265 ignores an empty Domain, also one that is only the leading dot.
    return value.lower().removeprefix(".") or None


def _expires(value: str | None) -> datetime | None:
    return internet_date(value, cookie=True) if value else None


def _max_age(value: str | None) -> int | None:
    if value is None or _MAX_AGE.fullmatch(value) is None:
        return None
    seconds = int(value)
    # Beyond SQLite's INTEGER, the Page's unit would fail to be written.
    return seconds if seconds in _INTEGER_RANGE else None
