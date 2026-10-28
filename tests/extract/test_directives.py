"""The directive, refresh and canonical columns of a Page (030-add-page-data, page-data; seam 4)."""

from datetime import UTC, datetime

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import FetchResult
from spider.crawl.pages.preparation import response_directives
from spider.crawl.urls import NormalizedUrl
from spider.extract.page_handler import page_rows
from spider.naming import DEFAULT_ROBOTS_TOKEN
from tests.support.page_data import page_row


def test_meta_robots_keeps_case_but_reads_directives() -> None:
    row = page_row(
        '<html><head><meta name="ROBOTS" content="NOINDEX, follow"><title>T</title></head>'
        "<body><p>Draft</p></body></html>"
    )

    assert (row.meta_robots, row.meta_robots_noindex, row.meta_robots_nofollow) == (
        "NOINDEX, follow",
        True,
        False,
    )


def test_x_robots_tag_is_stored_with_the_parsers_verdict() -> None:
    row = page_row(
        "<html><head><title>Staging</title></head><body><p>Not for search</p></body></html>",
        headers=(("X-Robots-Tag", "noindex"),),
    )

    assert (
        row.x_robots_tag,
        row.x_robots_tag_noindex,
        row.x_robots_tag_nofollow,
        row.meta_robots,
        row.meta_robots_noindex,
        row.meta_robots_nofollow,
    ) == ("noindex", True, False, None, False, False)


def test_x_robots_tag_is_kept_when_page_preparation_fails() -> None:
    # As the crawl engine records a 200 HTML response whose body was too large to prepare: its
    # directives come from its headers alone.
    response = FetchResult(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", "text/html"), ("X-Robots-Tag", "noindex")),
        body=b"<html><head><title>Big</title></head><body>" + b"<p>Row</p>" * 1000,
        fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
        response_time_ms=1,
    )
    result = UrlResult(
        url_id=1,
        url=NormalizedUrl("https://site.test/report"),
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
            headers=response.headers,
            fetched_at=response.fetched_at,
            response_time_ms=1,
            directives=response_directives(response, DEFAULT_ROBOTS_TOKEN),
        ),
        parsed=False,
        parse_error="body_too_large",
    )
    (row,) = page_rows(result)

    assert (
        row.x_robots_tag,
        row.x_robots_tag_noindex,
        row.meta_robots,
        row.meta_robots_noindex,
        row.meta_robots_nofollow,
    ) == ("noindex", True, None, None, None)


def test_http_refresh_header_is_a_redirect() -> None:
    row = page_row(
        "<html><head><title>Moved</title></head><body><p>This page has moved.</p></body></html>",
        headers=(("Refresh", "0; url=/new"),),
        url="https://example.test/old",
    )

    assert (row.redirect_type, row.redirect_url) == ("http_refresh", "https://example.test/new")


def test_a_refresh_of_the_page_itself_is_no_redirect() -> None:
    # A live blog that reloads itself every five minutes.
    row = page_row(
        "<html><head><title>Live</title></head><body><p>Updates</p></body></html>",
        headers=(("Refresh", "300; url=https://example.test/live"),),
        url="https://example.test/live",
    )

    assert (row.redirect_type, row.redirect_url) == (None, None)
