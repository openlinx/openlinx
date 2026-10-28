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


def test_meta_refresh_with_a_quoted_target() -> None:
    row = page_row(
        '<html><head><meta http-equiv="Refresh" content="5; URL=\'/new\'"><title>Old</title>'
        "</head><body><p>You will be taken to the new page.</p></body></html>",
        url="https://example.test/old",
    )

    assert (row.meta_refresh, row.redirect_type, row.redirect_url) == (
        "5; URL='/new'",
        "meta_refresh",
        "https://example.test/new",
    )


def test_only_the_first_meta_refresh_redirects() -> None:
    # A news page's five-minute reload, then a redirect a second template adds.
    row = page_row(
        '<html><head><meta http-equiv="refresh" content="300">'
        '<meta http-equiv="refresh" content="0; url=/new"><title>News</title></head>'
        "<body><p>Latest</p></body></html>",
        url="https://example.test/news",
    )

    assert (row.meta_refresh, row.redirect_type, row.redirect_url) == ("300", None, None)


def test_meta_refresh_without_a_target_is_not_a_redirect() -> None:
    row = page_row(
        '<html><head><meta http-equiv="refresh" content="30"><title>Scores</title></head>'
        "<body><p>Live scores</p></body></html>"
    )

    assert (row.meta_refresh, row.redirect_type) == ("30", None)


def test_relative_canonical_to_another_url() -> None:
    row = page_row(
        '<html><head><title>A</title><link rel="canonical" href="/b"></head>'
        "<body><p>Article</p></body></html>",
        url="https://example.test/a",
    )

    assert (row.canonical_url, row.canonical_count, row.canonical_relative) == (
        "https://example.test/b",
        1,
        True,
    )


def test_an_absolute_canonical_after_a_leading_space_is_not_relative() -> None:
    # As a template writes href="{{ ' ' }}{{ url }}": the URL parser removes the space.
    row = page_row(
        '<html><head><title>A</title><link rel="canonical" href=" https://example.test/b">'
        "</head><body><p>Article</p></body></html>",
        url="https://example.test/a",
    )

    assert (row.canonical_link_element_1, row.canonical_relative) == (
        "https://example.test/b",
        False,
    )


def test_html_and_header_canonicals_disagree() -> None:
    row = page_row(
        '<html><head><title>A</title><link rel="canonical" href="https://example.test/b">'
        "</head><body><p>Article</p></body></html>",
        headers=(("Link", '<https://example.test/c>; rel="canonical"'),),
        url="https://example.test/a",
    )

    assert (
        row.canonical_count,
        row.canonical_link_element_2,
        row.http_canonical,
        row.canonical_url,
    ) == (2, None, "https://example.test/c", None)


def test_canonical_after_an_image_in_head_is_ignored() -> None:
    row = page_row('<head><title>T</title><img src="x.png"><link rel="canonical" href="/b"></head>')

    assert row.canonical_count == 0


def test_base_element_changes_resolution() -> None:
    row = page_row(
        '<html><head><base href="https://example.test/docs/"><title>B</title>'
        '<link rel="canonical" href="page"></head><body><p>Docs</p></body></html>',
        url="https://example.test/a/b",
    )

    assert row.canonical_link_element_1 == "https://example.test/docs/page"


def test_pagination_from_html_and_header() -> None:
    row = page_row(
        '<html><head><title>Page 2</title><link rel="prev" href="/p1"></head>'
        "<body><p>Results 11-20</p></body></html>",
        headers=(("Link", '</p3>; rel="next"'),),
        url="https://example.test/p2",
    )

    assert (row.rel_prev_1, row.http_rel_next_1, row.rel_next_1, row.http_rel_prev_1) == (
        "https://example.test/p1",
        "https://example.test/p3",
        None,
        None,
    )


def test_rel_previous_is_a_previous_page() -> None:
    # The longer spelling that some paginating plugins write.
    row = page_row(
        '<html><head><title>Page 2</title><link rel="previous" href="/p1"></head>'
        "<body><p>Older posts</p></body></html>",
        url="https://example.test/p2",
    )

    assert row.rel_prev_1 == "https://example.test/p1"


def test_mobile_alternate_and_amp() -> None:
    row = page_row(
        '<html><head><title>A</title><link rel="alternate" media="only screen and '
        '(max-width: 640px)" href="https://m.example.test/a"><link rel="amphtml" href="/a.amp">'
        "</head><body><p>Article</p></body></html>",
        url="https://example.test/a",
    )

    assert (row.mobile_alternate_link, row.amphtml_link_element) == (
        "https://m.example.test/a",
        "https://example.test/a.amp",
    )
