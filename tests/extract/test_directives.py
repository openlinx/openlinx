"""The directive, refresh and canonical columns of a Page (030-add-page-data, page-data; seam 4)."""

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
