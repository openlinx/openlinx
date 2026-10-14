"""The Page handler: a URL's Page row from its UrlResult (030-add-page-data, page-data; seam 4)."""

from datetime import UTC, datetime
from typing import Any

from spider.crawl.hooks import UrlResult
from spider.crawl.urls import NormalizedUrl
from spider.extract.page_handler import page_rows
from spider.store.page_records import PageRow


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


def _fetched(url: str, **values: Any) -> UrlResult:
    return _result(
        url,
        fetch_state="fetched",
        status_code=200,
        content_type="text/html; charset=utf-8",
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
        fetch_error="timeout",
        fetch_error_message="No response within 20 s.",
        fetched_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert tuple(page_rows(failed)) == ()


def test_a_url_without_a_response_is_no_page_whatever_its_content_type() -> None:
    failed = _result(
        "http://site.test/reset",
        fetch_state="error",
        fetch_error="connection_error",
        content_type="text/html",
    )

    assert tuple(page_rows(failed)) == ()


def test_an_internal_url_outside_the_scope_is_not_a_page() -> None:
    assert tuple(page_rows(_fetched("https://site.test/blog/", in_scope=False))) == ()
