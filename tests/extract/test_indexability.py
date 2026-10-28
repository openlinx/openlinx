"""Indexability of a Page (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_row, unprepared_page_row


def test_plain_200_page_is_indexable() -> None:
    row = page_row(
        "<html><head><title>Plain</title></head><body><p>Just content</p></body></html>",
        url="https://example.test/plain",
    )

    assert (row.indexability, row.indexability_status) == ("indexable", None)


def test_noindex_wins_over_a_canonical() -> None:
    row = page_row(
        '<html><head><title>Old</title><meta name="robots" content="noindex">'
        '<link rel="canonical" href="https://example.test/new"></head>'
        "<body><p>Moved content</p></body></html>",
        url="https://example.test/old",
    )

    assert row.indexability_status == "noindex"


def test_self_referencing_canonical_stays_indexable() -> None:
    row = page_row(
        '<html><head><title>A</title><link rel="canonical" href="https://example.test/a"></head>'
        "<body><p>Article</p></body></html>",
        url="https://example.test/a",
    )

    assert row.indexability == "indexable"


def test_canonical_to_another_url() -> None:
    row = page_row(
        '<html><head><title>A</title><link rel="canonical" href="https://example.test/b"></head>'
        "<body><p>Article</p></body></html>",
        url="https://example.test/a",
    )

    assert row.indexability_status == "canonicalised"


def test_server_error() -> None:
    row = unprepared_page_row(status_code=503)

    assert row.indexability_status == "server_error"


def test_each_status_class_has_its_reason() -> None:
    # A redirect with an HTML body, a page removed for good, a transforming proxy's 2xx, a bot
    # block such as LinkedIn's 999, and the last server error code.
    statuses = {
        301: unprepared_page_row(status_code=301).indexability_status,
        410: unprepared_page_row(status_code=410).indexability_status,
        203: page_row("<p>Proxied</p>", status_code=203).indexability_status,
        999: unprepared_page_row(status_code=999).indexability_status,
        599: unprepared_page_row(status_code=599).indexability_status,
    }

    assert statuses == {
        301: "redirected",
        410: "client_error",
        203: None,
        999: "client_error",
        599: "server_error",
    }


def test_robots_txt_beats_the_status_code() -> None:
    # Fetched under --ignore-robots, so the response exists while robots.txt disallows it.
    row = unprepared_page_row(status_code=404, blocked_by_robots_txt=True)

    assert row.indexability_status == "blocked_by_robots_txt"
