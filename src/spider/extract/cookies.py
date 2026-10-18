"""A Page's cookies from its Set-Cookie headers, without their values (030-add-page-data D14)."""

from spider.store.page_records import CookieRow, SameSite

_SAME_SITE: dict[str, SameSite] = {"strict": "strict", "lax": "lax", "none": "none"}


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
        domain=attributes.get("domain"),
        path=attributes.get("path"),
        secure="secure" in attributes,
        http_only="httponly" in attributes,
        same_site=_SAME_SITE.get((attributes.get("samesite") or "").lower()),
    )
