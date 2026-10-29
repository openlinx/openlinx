"""Link attributes (030-add-page-data, page-data; seam 4)."""

from tests.support.page_data import page_link_rows


def test_hyperlink_with_rel_flags() -> None:
    (row,) = page_link_rows(
        '<main><a href="/b" rel="nofollow UGC">Read  more</a></main>', url="https://example.test/a"
    )

    assert (
        row.type,
        row.target,
        row.anchor_text,
        row.rel,
        row.rel_nofollow,
        row.rel_ugc,
        row.rel_sponsored,
        row.declared_in,
    ) == (
        "hyperlink",
        "https://example.test/b",
        "Read more",
        "nofollow ugc",
        True,
        True,
        False,
        "body",
    )
