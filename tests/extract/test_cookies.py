"""Cookie rows from a Page's Set-Cookie headers (030-add-page-data, page-data; seam 4)."""

from datetime import UTC, datetime

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.pages.directives import NO_DIRECTIVES
from spider.crawl.urls import NormalizedUrl
from spider.extract.page_handler import cookie_rows, page_rows
from spider.store.page_records import CookieRow


def _result(*set_cookies: str, headers: tuple[tuple[str, str], ...] = ()) -> UrlResult:
    return UrlResult(
        url_id=1,
        url=NormalizedUrl("https://example.test/"),
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
        fetch_state="fetched",
        response=UrlResponse(
            status_code=200,
            reason="OK",
            content_type="text/html",
            headers=(
                ("Content-Type", "text/html"),
                *headers,
                *(("Set-Cookie", value) for value in set_cookies),
            ),
            fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
            response_time_ms=1,
            directives=NO_DIRECTIVES,
        ),
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
    # The second header as a proxy that appends its own SameSite sends it.
    rows = _cookies(
        "a=1; Path=/x; secure; PATH=/y; samesite=STRICT",
        "sid=1; Path=/; SameSite=Lax; Secure; SameSite=None",
    )

    assert [(row.path, row.secure, row.same_site) for row in rows] == [
        ("/y", True, "strict"),
        ("/", True, "none"),
    ]


def test_a_repeated_attribute_that_does_not_parse_keeps_the_valid_one() -> None:
    # The empty values a template leaves when its variable is unset.
    rows = _cookies(
        "sid=1; Max-Age=3600; Max-Age=",
        "sid=1; Domain=example.test; Domain=",
        "sid=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Expires=",
    )

    assert [(row.max_age, row.domain, row.expires) for row in rows] == [
        (3600, None, None),
        (None, "example.test", None),
        (None, None, datetime(2026, 10, 21, 7, 28, tzinfo=UTC)),
    ]


def test_cookie_count_matches_the_headers() -> None:
    # HTTP/1.1 servers and proxies such as Node and Envoy send header names in lowercase.
    result = _result(
        headers=(("Set-Cookie", "a=1; Max-Age=3600"), ("set-cookie", "b=2; Domain=.Example.test"))
    )
    (page,) = page_rows(result)
    first, second = cookie_rows(result)

    assert (page.set_cookie_count, first.max_age, second.domain) == (2, 3600, "example.test")


def test_a_max_age_beyond_64_bits_is_clamped_and_a_malformed_one_is_null() -> None:
    rows = _cookies(
        "a=1; Max-Age=-1",
        "b=1; Max-Age=1.5",
        "c=1; Max-Age=+3600",
        "d=1; Max-Age=99999999999999999999",
        "e=1; Max-Age=-99999999999999999999",
    )

    assert [row.max_age for row in rows] == [-1, None, None, 2**63 - 1, -(2**63)]


def test_an_empty_domain_is_null() -> None:
    (row,) = _cookies("a=1; Domain=")

    assert row.domain is None


def test_a_path_without_a_value_is_null() -> None:
    rows = _cookies("a=1; Path", "b=1; Path=", "c=1; Path=docs")

    assert [row.path for row in rows] == [None, None, None]


def test_a_folded_header_stores_no_value_in_domain_or_path() -> None:
    # An API gateway joins two Set-Cookie headers into one with ", ".
    rows = _cookies("lang=en; Domain=example.com, sid=SECRET", "lang=en; Path=/, sid=SECRET")

    assert [(row.domain, row.path) for row in rows] == [(None, None), (None, None)]


def test_a_domain_is_a_host_name_or_an_ip_address() -> None:
    rows = _cookies(
        "a=1; Domain=.Shop.Example.test",
        "b=1; Domain=192.0.2.10",
        "c=1; Domain=2001:db8::1",
        "d=1; Domain=example.test/path",
    )

    assert [row.domain for row in rows] == ["shop.example.test", "192.0.2.10", "2001:db8::1", None]


def test_expires_reads_two_digit_years_as_rfc_6265_does() -> None:
    rows = _cookies(
        "a=1; Expires=Wed, 21-Oct-15 07:28:00 GMT",
        "b=1; Expires=Thu, 01-Jan-70 00:00:01 GMT",
        "c=1; Expires=Tue, 01-Jan-69 00:00:00 GMT",
        "d=1; Expires=soon",
    )

    assert [row.expires for row in rows] == [
        datetime(2015, 10, 21, 7, 28, tzinfo=UTC),
        datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC),
        datetime(2069, 1, 1, tzinfo=UTC),
        None,
    ]


def test_partitioned_is_a_flag() -> None:
    rows = _cookies("a=1; Partitioned", "b=1")

    assert [row.partitioned for row in rows] == [True, False]
