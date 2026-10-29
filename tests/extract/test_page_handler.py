"""The Page handler: a URL's Page row from its UrlResult (030-add-page-data, page-data; seam 4)."""

from datetime import UTC, datetime
from typing import Any

from openlinx.crawl.engine.hooks import UrlFailure, UrlResponse, UrlResult
from openlinx.crawl.pages.directives import NO_DIRECTIVES
from openlinx.crawl.urls import NormalizedUrl
from openlinx.extract.page_handler import page_rows
from openlinx.store.page_records import PageRow
from tests.support.headers import LAST_MODIFIEDS


def _result(
    url: str, *, is_internal: bool = True, in_scope: bool = True, **values: Any
) -> UrlResult:
    """A URL as the engine gives it to handlers: Internal and in the Scope unless said otherwise."""
    return UrlResult(
        url_id=1,
        url=NormalizedUrl(url),
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=is_internal,
        in_scope=in_scope,
        **values,
    )


def _fetched(
    url: str,
    *,
    headers: tuple[tuple[str, str], ...] = (("Content-Type", "text/html; charset=utf-8"),),
    status_code: int = 200,
    reason: str = "OK",
    **values: Any,
) -> UrlResult:
    return _result(
        url,
        fetch_state="fetched",
        response=UrlResponse(
            status_code=status_code,
            reason=reason,
            content_type="text/html; charset=utf-8",
            headers=headers,
            fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
            response_time_ms=1,
            directives=NO_DIRECTIVES,
        ),
        **values,
    )


def _page(result: UrlResult) -> PageRow:
    (row,) = page_rows(result)
    return row


def test_non_ascii_path_is_decoded_for_display() -> None:
    row = _page(_fetched("https://example.test/%C3%BCber%20uns"))

    assert (row.url_encoded_address, row.address) == (
        "https://example.test/%C3%BCber%20uns",
        "https://example.test/über%20uns",
    )


def test_punycode_host_is_shown_in_unicode() -> None:
    assert _page(_fetched("https://xn--bcher-kva.test/")).address == "https://bücher.test/"


def test_invisible_and_control_characters_stay_encoded() -> None:
    row = _page(_fetched("https://example.test/a%C2%A0b%E2%80%AEc%C2%9Bd%C3%BC"))

    assert row.address == "https://example.test/a%C2%A0b%E2%80%AEc%C2%9Bdü"


def test_path_and_query_of_the_address() -> None:
    rows = [
        _page(_fetched(url))
        for url in (
            "https://example.test/%D0%9A%D0%B0%D1%82/a%2Fb?x=1&y=%C3%BC",
            "https://example.test/a?",
            "https://example.test/a",
        )
    ]

    assert [(row.url_path, row.url_query) for row in rows] == [
        ("/Кат/a%2Fb", "x=1&y=ü"),
        ("/a", ""),
        ("/a", None),
    ]


def test_last_modified_is_normalised_to_a_timestamp() -> None:
    row = _page(
        _fetched(
            "https://example.test/", headers=(("Last-Modified", "Wed, 21 Oct 2015 07:28:00 GMT"),)
        )
    )

    assert row.last_modified == datetime(2015, 10, 21, 7, 28, tzinfo=UTC)


def test_invalid_last_modified_is_null() -> None:
    row = _page(_fetched("https://example.test/", headers=(("Last-Modified", "yesterday"),)))

    assert row.last_modified is None


def test_real_last_modified_headers_give_their_times() -> None:
    assert {entry.stack: _last_modified(entry.header) for entry in LAST_MODIFIEDS} == {
        entry.stack: entry.time for entry in LAST_MODIFIEDS
    }


def test_reason_phrase_falls_back_to_the_standard_phrase() -> None:
    # The fetcher records an empty reason for the status line `HTTP/1.1 404`.
    row = _page(_fetched("https://example.test/missing", status_code=404, reason=""))

    assert row.status == "Not Found"


def test_a_sent_reason_phrase_is_kept_and_a_missing_one_comes_from_the_registry() -> None:
    def status(status_code: int, reason: str) -> str | None:
        result = _fetched("https://example.test/", status_code=status_code, reason=reason)
        return _page(result).status

    # A server's own phrase, as a localised one sends it; a rate limiter's and a body-size
    # limit's bare status lines; a code the registry leaves unassigned, and one it lists unused.
    assert [
        status(404, "Nicht Gefunden"),
        status(429, ""),
        status(413, ""),
        status(299, ""),
        status(418, ""),
    ] == ["Nicht Gefunden", "Too Many Requests", "Content Too Large", None, None]


def _last_modified(value: str, name: str = "Last-Modified") -> datetime | None:
    return _page(_fetched("https://example.test/", headers=((name, value),))).last_modified


def test_the_obsolete_http_date_forms_are_read_as_gmt() -> None:
    assert [
        _last_modified("Sunday, 06-Nov-94 08:49:37 GMT"),
        _last_modified("Sun Nov  6 08:49:37 1994"),
    ] == [datetime(1994, 11, 6, 8, 49, 37, tzinfo=UTC)] * 2


def test_the_first_last_modified_header_wins() -> None:
    # The application's header, then the one a cache in front of it appended.
    headers = (
        ("Last-Modified", "Wed, 21 Oct 2015 07:28:00 GMT"),
        ("Last-Modified", "Thu, 22 Oct 2015 09:00:00 GMT"),
    )

    row = _page(_fetched("https://example.test/", headers=headers))

    assert row.last_modified == datetime(2015, 10, 21, 7, 28, tzinfo=UTC)


def test_last_modified_is_read_in_any_letter_case() -> None:
    assert _last_modified("Wed, 21 Oct 2015 07:28:00 GMT", name="last-MODIFIED") == datetime(
        2015, 10, 21, 7, 28, tzinfo=UTC
    )


def test_a_last_modified_offset_is_converted_to_utc() -> None:
    moment = _last_modified("Wed, 21 Oct 2015 07:28:00 +0300")

    assert (moment, moment and moment.tzinfo) == (datetime(2015, 10, 21, 4, 28, tzinfo=UTC), UTC)


def test_a_last_modified_beyond_the_timestamp_range_is_null() -> None:
    # The year 9999 at -01:00 is the year 10000 in UTC, which the timestamp column cannot hold.
    assert _last_modified("Fri, 31 Dec 9999 23:59:59 -0100") is None


def test_an_address_keeps_what_does_not_decode() -> None:
    row = _page(_fetched("https://xn--bcher-kva.xn--zz.test:8080/%FF%C3%BC%2F?q=%E2%82"))

    assert row.address == "https://bücher.xn--zz.test:8080/%FFü%2F?q=%E2%82"


def test_url_blocked_by_robots_txt_is_not_a_page() -> None:
    blocked = _result(
        "http://site.test/private/x", fetch_state="skipped", skip_reason="blocked_by_robots_txt"
    )

    assert tuple(page_rows(blocked)) == ()


def test_url_without_a_response_is_not_a_page() -> None:
    failed = _result(
        "http://site.test/timeout",
        fetch_state="error",
        failure=UrlFailure(
            fetch_error="timeout",
            fetch_error_message="No response within 20 s.",
            fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        ),
    )

    assert tuple(page_rows(failed)) == ()


def test_an_internal_url_outside_the_scope_is_not_a_page() -> None:
    assert tuple(page_rows(_fetched("https://site.test/blog/", in_scope=False))) == ()
