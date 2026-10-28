"""Indexability of a Page (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_row


def test_plain_200_page_is_indexable() -> None:
    row = page_row(
        "<html><head><title>Plain</title></head><body><p>Just content</p></body></html>",
        url="https://example.test/plain",
    )

    assert (row.indexability, row.indexability_status) == ("indexable", None)
