"""Indexability of a Page (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_row


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
