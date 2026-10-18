"""Cookie rows from a Page's Set-Cookie headers (030-add-page-data, page-data; seam 4)."""

from datetime import UTC, datetime

from spider.crawl.hooks import UrlResult
from spider.crawl.urls import NormalizedUrl
from spider.extract.page_handler import cookie_rows
from spider.store.page_records import CookieRow


def _result(*set_cookies: str) -> UrlResult:
    return UrlResult(
        url_id=1,
        url=NormalizedUrl("https://example.test/"),
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        status_code=200,
        content_type="text/html",
        response_time_ms=1,
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        headers=tuple(("Set-Cookie", value) for value in set_cookies),
    )


def _cookies(*set_cookies: str) -> list[CookieRow]:
    return list(cookie_rows(_result(*set_cookies)))


def test_cookie_attributes_are_stored() -> None:
    (row,) = _cookies("sid=abc123; Path=/; Secure; HttpOnly; SameSite=Lax")

    assert (row.name, row.path, row.secure, row.http_only, row.same_site, row.domain) == (
        "sid",
        "/",
        True,
        True,
        "lax",
        None,
    )


def test_a_cookie_without_an_equals_sign_has_an_empty_name() -> None:
    (row,) = _cookies("abc123; Path=/")

    assert (row.name, row.path) == ("", "/")


def test_a_repeated_attribute_takes_the_last_in_any_letter_case() -> None:
    (row,) = _cookies("a=1; Path=/x; secure; PATH=/y; samesite=STRICT")

    assert (row.path, row.secure, row.same_site) == ("/y", True, "strict")
