"""The Page handler: a URL's Page row from its UrlResult (030-add-page-data, page-data; seam 4)."""

from typing import Any

from spider.crawl.hooks import UrlResult
from spider.crawl.urls import NormalizedUrl
from spider.extract.page_handler import page_rows
from spider.store.page_records import PageRow


def _fetched(url: str, **values: Any) -> UrlResult:
    """A fetched Internal HTML URL in the Scope, as the engine gives it to handlers."""
    return UrlResult(
        url_id=1,
        url=NormalizedUrl(url),
        crawl_depth=0,
        discovered_via="seed",
        found_on_url_id=None,
        is_internal=True,
        in_scope=True,
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


def test_an_address_keeps_what_does_not_decode() -> None:
    row = _page(_fetched("https://xn--bcher-kva.xn--zz.test:8080/%FF%C3%BC%2F?q=%E2%82"))

    assert row.address == "https://bücher.xn--zz.test:8080/%FFü%2F?q=%E2%82"
